"""Tom 2026-11-23: one combined observation per chunk; all reactions P5;
a 15 s window; Aigel off -> unexplained events go straight to the Noob."""
import json
import os
import unittest

try:
    from . import harness as hm, ranker as rk, trigger, agent_link
except ImportError:
    import harness as hm, ranker as rk, trigger, agent_link

NOOBIA = os.environ.get("NOOBIA", "/noobia")
PATTERNS = os.path.join(NOOBIA, "lynx", "autonomy", "patterns-lynx.json")


class Adapter:
    def __init__(self):
        self.messages = []

    def deliver(self, m):
        agent_link.validate(m)
        self.messages.append(m)
        return {"status": "delivered", "id": m["id"], "detail": ""}


class Aigel:
    def __init__(self):
        self.chunks = []

    def send_chunk(self, chunk):
        self.chunks.append(chunk)
        return {"decision": "quiet", "message": None, "patterns": [], "note": ""}


class CombineTest(unittest.TestCase):
    def make(self, aigel_enabled=False):
        self.t = [1000.0]
        self.feed = []
        self.adapter, self.aigel = Adapter(), Aigel()
        with open(PATTERNS) as f:
            store = json.load(f)["store"]
        r = rk.Ranker(store)

        def read_new():
            out, self.feed[:] = list(self.feed), []
            return out
        return hm.Harness(host="lynx", read_new=read_new,
                          chunker=trigger.Chunker(window_s=15, max_lines=15, uniform_priority=5,
                                                  carry_priority=False),
                          client=self.aigel, adapter=self.adapter, ranker=r,
                          clock=lambda: self.t[0], combine=True, aigel_enabled=aigel_enabled)

    def test_five_events_of_any_kind_make_one_message(self):
        h = self.make()
        self.feed += [
            "NOOBIA P1 touch tap count=1 dur_ms=90 | a tap",
            "NOOBIA P1 light bright raw=14 | bright",
            "NOOBIA P1 light dark raw=1 | dark",
            "NOOBIA P1 camera objects.seen cam=wide n=1 | laptop(0.97) ~ a laptop on a desk",
        ]
        h.step()
        self.assertEqual(self.adapter.messages, [], "four P5 lines wait")
        self.feed.append("NOOBIA P1 light bright raw=15 | bright")   # the 5th, a repeat
        h.step()
        self.assertEqual(len(self.adapter.messages), 1)
        text = self.adapter.messages[0]["text"]
        self.assertIn("tapped", text)
        self.assertIn("laptop", text)
        self.assertEqual(text.count("became bright"), 1, "unique sentences only: " + text)

    def test_single_event_goes_after_the_window(self):
        h = self.make()
        self.feed.append("NOOBIA P1 touch tap count=1 dur_ms=90 | a tap")
        h.step()
        self.assertEqual(self.adapter.messages, [])
        self.t[0] += 16
        h.step()
        self.assertEqual(len(self.adapter.messages), 1, "not carried after the 15 s window")

    def test_aigel_off_sends_unexplained_events_to_the_noob(self):
        h = self.make(aigel_enabled=False)
        self.feed += ["NOOBIA P1 mystery thing x=1 | something strange happened",
                      "NOOBIA P0 motion status.sample x=1 | routine",
                      "NOOBIA P20 wifi status.sample signal=-60 | routine p20 sample"]
        h.step(); self.t[0] += 16; h.step()
        self.assertEqual(len(self.adapter.messages), 1)
        self.assertIn("something strange happened", self.adapter.messages[0]["text"])
        self.assertNotIn("routine", self.adapter.messages[0]["text"])   # P0 and P20 samples
        self.assertEqual(self.aigel.chunks, [])

    def test_window_expands_and_buffers_while_agent_is_busy(self):
        busy = [True]
        h = self.make(aigel_enabled=False)
        h.chunker.is_busy = lambda: busy[0]
        # Arrive while busy
        self.feed.append("NOOBIA P1 mystery thing x=1 | event one")
        h.step()
        self.t[0] += 30  # Wait beyond 15s window while busy
        self.feed.append("NOOBIA P1 mystery thing x=2 | event two")
        h.step()
        # Should not have delivered yet because agent is busy queueing
        self.assertEqual(len(self.adapter.messages), 0)
        # Agent becomes ready
        busy[0] = False
        h.step()
        # Window closed and delivered both events together!
        self.assertEqual(len(self.adapter.messages), 1)
        self.assertIn("event one", self.adapter.messages[0]["text"])
        self.assertIn("event two", self.adapter.messages[0]["text"])

    def test_aigel_on_gets_the_unexplained(self):
        h = self.make(aigel_enabled=True)
        self.feed.append("NOOBIA P1 mystery thing x=1 | something strange happened")
        h.step(); self.t[0] += 16; h.step(); self.t[0] += 2; h.step()
        self.assertEqual(self.adapter.messages, [])
        self.assertEqual(len(self.aigel.chunks), 1)


class SlowAigelTest(CombineTest):
    def test_slow_aigel_never_blocks_the_noob(self):
        import threading, time
        gate = threading.Event()
        h = self.make(aigel_enabled=True)
        h.async_aigel = True
        def slow(chunk):
            gate.wait(5)
            self.aigel.chunks.append(chunk)
            return {"decision": "message", "message": "Aigel says hi.", "patterns": [], "note": ""}
        self.aigel.send_chunk = slow
        self.feed.append("NOOBIA P1 mystery thing x=1 | strange")
        h.step(); self.t[0] += 16; h.step(); self.t[0] += 2; h.step()   # Aigel now thinking
        self.feed += ["NOOBIA P1 touch tap count=1 dur_ms=90 | a tap"] * 5
        h.step()
        self.assertEqual(len(self.adapter.messages), 1, "the tap got through while Aigel thinks")
        gate.set(); time.sleep(0.2); h.step()
        self.assertEqual([m["text"] for m in self.adapter.messages][-1], "Aigel says hi.")
        self.assertEqual(len(h.queue), 0)


if __name__ == "__main__":
    unittest.main()
