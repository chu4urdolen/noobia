"""Tests for the host autonomy loop (harness.py) with real chunker and ranker, fake I/O."""

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import agent_link  # noqa: E402
import harness as hm  # noqa: E402
import ranker as rk  # noqa: E402
import sense  # noqa: E402
import trigger  # noqa: E402

CAT = sense.format_line(1, "camera", "object.seen", {"label": "cat", "conf": "0.91"}, "cat")
DOG = sense.format_line(1, "camera", "object.seen", {"label": "dog", "conf": "0.88"}, "dog")


def cat_pattern():
    return {"id": "cat-seen", "match": {"sense": "camera", "event": "object.seen",
                                        "fields": {"label": "cat"}, "text_contains": None},
            "message": "A cat appeared in front of you", "to_noob": True, "cooldown_s": 300,
            "examples": {"must": ["NOOBIA P1 camera object.seen label=cat conf=0.9"],
                         "must_not": ["NOOBIA P1 camera object.seen label=dog conf=0.9"]},
            "hits": 0, "last_hit": None, "origin": "human"}


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class FakeAigel:
    def __init__(self, reply=None):
        self.reply = reply or {"decision": "quiet", "message": None, "patterns": [], "note": ""}
        self.chunks, self.down = [], False

    def send_chunk(self, chunk):
        if self.down:
            raise ConnectionError("Nexus unreachable")
        self.chunks.append(chunk)
        return dict(self.reply)


class FakeAdapter:
    def __init__(self):
        self.messages = []

    def deliver(self, message):
        agent_link.validate(message)
        self.messages.append(message)
        return {"status": "delivered", "id": message["id"], "detail": ""}


class HarnessTest(unittest.TestCase):
    def setUp(self):
        self.clock, self.aigel, self.adapter = Clock(), FakeAigel(), FakeAdapter()
        self.inbox, self.logs, self.emitted, self.rules = [], [], [], []

    def make(self, ranker=True, **kw):
        def read_new():
            out, self.inbox[:] = list(self.inbox), []
            return out
        r = rk.Ranker([cat_pattern()]) if ranker else None
        return hm.Harness(host="lynx", read_new=read_new, chunker=trigger.Chunker(),
                          client=self.aigel, adapter=self.adapter, ranker=r,
                          emit=self.emitted.append, log=self.logs.append,
                          on_priority_rules=self.rules.extend,
                          validate_pattern=lambda p: rk.validate_pattern(p, []),
                          clock=self.clock, **kw)

    # --- kill switch (Aria's IS-2 review #340) ---------------------------
    def test_kill_switch_drops_a_chunk_already_queued_and_sends_nothing(self):
        self.aigel.down = True                      # first send fails -> chunk stays queued
        h = self.make(disabled=lambda: self.off)
        self.off = False
        self.inbox.append(DOG)
        h.step()
        self.assertEqual(len(h.queue), 1)
        self.aigel.down = False
        self.off = True
        self.clock.t += 400                         # past any backoff
        summary = h.step()
        self.assertEqual(self.aigel.chunks, [])     # Aria's reproduction: was sent once
        self.assertEqual(len(h.queue), 0)
        self.assertTrue(summary["disabled"])
        self.assertEqual(self.adapter.messages, [])
        self.assertEqual(sum("disabled by kill switch" in l for l in self.logs), 1)

    def test_kill_switch_discards_new_lines_and_reenable_does_not_replay_them(self):
        self.off = True
        h = self.make(disabled=lambda: self.off)
        self.inbox.append(DOG)
        h.step()
        self.clock.t += 120
        h.step(); h.step()
        self.assertEqual(sum("disabled by kill switch" in l for l in self.logs), 1)  # one notice
        self.off = False
        self.clock.t += 120
        h.step()
        self.assertEqual(self.aigel.chunks, [])     # the dog seen while disabled is never sent
        self.assertTrue(any("re-enabled" in l for l in self.logs))
        self.inbox.append(DOG)                      # a fresh line after re-enable works normally
        h.step()
        self.assertEqual(len(self.aigel.chunks), 1)

    def test_reenable_discards_a_chunk_that_was_open_before_the_switch(self):
        self.off = False
        h = self.make(disabled=lambda: self.off)
        self.inbox.append(sense.format_line(0, "wifi", "status.sample", {"dbm": "-60"}))
        h.step()                                    # opens a chunk, nothing closes yet
        self.off = True
        h.step()
        self.off = False
        self.clock.t += 600                         # long past the 60 s timeout
        h.step()
        self.assertEqual(self.aigel.chunks, [])     # the pre-switch line never surfaces
        # control: without the switch, the same line DOES go to Aigel on timeout
        self.inbox.append(sense.format_line(0, "wifi", "status.sample", {"dbm": "-60"}))
        h.step()
        self.clock.t += 600
        h.step()
        self.assertEqual(len(self.aigel.chunks), 1)

    def test_known_priority_line_is_explained_without_aigel(self):
        h = self.make()
        self.inbox.append(CAT)
        h.step()
        self.assertEqual([m["text"] for m in self.adapter.messages], ["A cat appeared in front of you"])
        self.assertEqual(self.adapter.messages[0]["source"], "ranker")
        self.assertEqual(self.adapter.messages[0]["pattern_id"], "cat-seen")
        self.assertEqual(self.aigel.chunks, [])

    def test_unknown_priority_line_goes_to_aigel_and_her_message_is_delivered(self):
        self.aigel.reply = {"decision": "message", "message": "A dog is in front of you",
                            "patterns": [], "note": "new label"}
        h = self.make()
        self.inbox.append(DOG)
        h.step()
        self.assertEqual(len(self.aigel.chunks), 1)
        self.assertEqual(self.aigel.chunks[0]["reason"], "priority")
        self.assertEqual(self.adapter.messages[-1]["source"], "aigel")
        self.assertIn("label=dog", self.adapter.messages[-1]["evidence"][0])

    def test_timeout_chunk_goes_straight_to_aigel_and_quiet_delivers_nothing(self):
        h = self.make()
        self.inbox.append(sense.format_line(0, "battery", "level", {"pct": 70}))
        h.step()
        self.clock.t = 61
        h.step()
        self.assertEqual([c["reason"] for c in self.aigel.chunks], ["timeout"])
        self.assertEqual(self.adapter.messages, [])

    def test_aigel_down_queues_then_retries(self):
        self.aigel.down = True
        h = self.make()
        self.inbox.append(DOG)
        summary = h.step()
        self.assertEqual(summary["queued"], 1)
        self.assertTrue(any("send failed" in l for l in self.logs))
        self.aigel.down = False
        self.clock.t = 5
        self.assertEqual(h.step()["queued"], 0)
        self.assertEqual(len(self.aigel.chunks), 1)

    def test_failures_back_off_exponentially_and_reset_on_success(self):
        self.aigel.down = True
        attempts = []
        orig = self.aigel.send_chunk

        def counting(chunk):
            attempts.append(self.clock.t)
            return orig(chunk)
        self.aigel.send_chunk = counting
        h = self.make()
        self.inbox.append(DOG)
        for t in range(0, 120):
            self.clock.t = float(t)
            h.step()
        self.assertEqual(attempts, [0.0, 2.0, 6.0, 14.0, 30.0, 62.0])   # 2, 4, 8, 16, 32 s gaps
        self.aigel.down = False
        self.clock.t = 200.0
        h.step()
        self.assertEqual((h.failures, len(self.aigel.chunks)), (0, 1))

    def test_backoff_is_capped(self):
        self.aigel.down = True
        h = self.make()
        self.inbox.append(DOG)
        for _ in range(30):
            self.clock.t = h.retry_at
            h.step()
        self.assertEqual(h.failures, 30)
        self.assertEqual(h.retry_at - self.clock.t, 300.0)   # capped at max_backoff_s

    def test_queue_bounded_drops_oldest(self):
        self.aigel.down = True
        h = self.make(queue_max=3)
        for i in range(5):
            self.inbox.append(sense.format_line(1, "camera", "object.seen", {"label": f"x{i}"}))
            self.clock.t = i
            h.step()
        self.assertEqual((len(h.queue), h.dropped), (3, 2))
        self.assertIn("label=x4", h.queue[-1]["lines"][0]["raw"])

    def test_rate_limits(self):
        h = self.make(max_per_hour=2, min_interval_s=1.0)
        for i in range(4):
            self.inbox.append(sense.format_line(1, "camera", "object.seen", {"label": f"y{i}"}))
        h.step()                                    # 4 chunks closed, 1 sent (min interval)
        self.assertEqual(len(self.aigel.chunks), 1)
        self.clock.t = 2
        h.step()
        self.assertEqual(len(self.aigel.chunks), 2)
        self.clock.t = 4
        h.step()
        self.assertEqual(len(self.aigel.chunks), 2)  # hourly cap reached
        self.clock.t = 3602
        h.step()
        self.assertEqual(len(self.aigel.chunks), 3)

    def test_aigel_patterns_are_validated_before_use(self):
        good = cat_pattern() | {"id": "dog-seen", "message": "A dog appeared",
                                "match": {"sense": "camera", "event": "object.seen",
                                          "fields": {"label": "dog"}, "text_contains": None},
                                "examples": {"must": ["NOOBIA P1 camera object.seen label=dog conf=0.9"],
                                             "must_not": ["NOOBIA P1 camera object.seen label=cat conf=0.9"]},
                                "origin": "aigel"}
        bad = cat_pattern() | {"id": "blind", "examples": {"must": [], "must_not": []}}
        self.aigel.reply = {"decision": "quiet", "message": None, "patterns": [good, bad], "note": ""}
        h = self.make()
        h.ranker.add_pattern = lambda p: h.ranker.store.append(p)  # until Banshee's R4 lands
        self.inbox.append(DOG)
        h.step()
        self.assertIn("dog-seen", [p["id"] for p in h.ranker.store])
        self.assertTrue(any("pattern rejected id=blind" in l or "pattern added id=blind" not in l
                            for l in self.logs))
        self.assertTrue(any("pattern added id=dog-seen" in l for l in self.logs))

    def test_priority_rules_handed_to_prioritizer(self):
        self.aigel.reply = {"decision": "quiet", "message": None, "patterns": [], "note": "",
                            "priority_rules": [{"id": "wifi-down"}]}
        h = self.make()
        self.inbox.append(DOG)
        h.step()
        self.assertEqual(self.rules, [{"id": "wifi-down"}])

    def test_heartbeat_is_emitted_and_never_wakes_aigel(self):
        h = self.make(heartbeat_s=300)
        h.step()
        self.assertEqual(len(self.emitted), 1)
        self.assertIn("NOOBIA P0 autonomy heartbeat", self.emitted[0])
        for t in range(1, 2000, 60):                 # heartbeats come back through the view
            self.clock.t = float(t)
            self.inbox.append(self.emitted[-1])
            h.step()
        self.assertEqual(self.aigel.chunks, [])
        self.assertGreater(len(self.emitted), 5)

    def test_silence_is_reported_directly_once(self):
        h = self.make(silence_s=900)
        self.clock.t = 901
        h.step()
        self.assertEqual([c["reason"] for c in self.aigel.chunks], ["silent"])
        self.assertEqual(self.aigel.chunks[0]["lines"][0]["event"], "view.silent")
        self.clock.t = 2000
        h.step()
        self.assertEqual(len(self.aigel.chunks), 1)  # not repeated while still silent

    def test_without_ranker_priority_chunks_go_to_aigel(self):
        h = self.make(ranker=False)
        self.inbox.append(CAT)
        h.step()
        self.assertEqual(len(self.aigel.chunks), 1)
        self.assertEqual(self.adapter.messages, [])

    def test_kill_switch_through_chunker_sends_nothing(self):
        h = self.make()
        h.chunker = trigger.Chunker(disabled=lambda: True)
        self.inbox.append(CAT)
        h.step()
        self.assertEqual((self.adapter.messages, self.aigel.chunks), ([], []))


if __name__ == "__main__":
    unittest.main()
