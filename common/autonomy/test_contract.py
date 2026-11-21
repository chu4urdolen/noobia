"""Conformance tests for the Noobia autonomy contract (ARCHITECTURE.md v0.1).

Written first (task E0) as the target for E1-E3. Each block skips until its
module exists; once a module lands, every test in its block must pass.
Change a test only together with ARCHITECTURE.md and a forge note.

Required interfaces:

sense.py
  format_line(p: int, sense: str, event: str, fields: dict | None = None,
              text: str = "") -> str          # raises ValueError on bad input
  parse_line(line: str) -> dict | None        # None for non-sense lines;
      # dict keys: p, sense, event, fields (dict), text, self_caused (bool)

trigger.py
  Chunker(window_s=60, max_lines=15, max_chunk_lines=200, max_bytes=32768,
          disabled=lambda: False)
    .feed(line: str, now: float) -> list[list[dict]]   # closed chunks
    .tick(now: float) -> list[list[dict]]              # closes on time
    # chunks hold parsed lines (sense.parse_line dicts)

ranker.py
  validate_pattern(regex: str, example: str, corpus: list[str]) -> None
      # raises ValueError if unsafe, if it misses its example, or if it
      # matches any corpus line
  Ranker(patterns: list[dict], capacity=100)
    .process(chunk: list[dict], now: float) -> dict with keys
        explained: list[(line_dict, pattern_id)]
        unexplained: list[line_dict]
        messages: list[str]      # deliverable, after cooldowns
    .patterns -> list[dict]      # current ranked store (<= capacity)
    .archive  -> list[dict]      # retired, never silently deleted
  pattern dict: id, regex, sense, event, message, to_noob, cooldown_s,
                hits, last_hit, origin
"""

import importlib
import unittest

HERE = __import__("pathlib").Path(__file__).resolve().parent
__import__("sys").path.insert(0, str(HERE))


def need(name):
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError:
        raise unittest.SkipTest(f"{name}.py not implemented yet (contract target)")


class SenseLineContract(unittest.TestCase):
    def setUp(self):
        self.s = need("sense")

    def test_canonical_format(self):
        line = self.s.format_line(1, "wifi", "link.down", {"ssid": "Noobia"},
                                  "Noobia Wi-Fi dropped")
        self.assertEqual(line, "NOOBIA P1 wifi link.down ssid=Noobia | Noobia Wi-Fi dropped")
        self.assertEqual(self.s.format_line(0, "battery", "level", {"pct": 71}),
                         "NOOBIA P0 battery level pct=71")

    def test_round_trip(self):
        line = self.s.format_line(3, "touch", "tap", {"x": 540, "y": 1200}, "Screen tapped")
        parsed = self.s.parse_line(line)
        self.assertEqual((parsed["p"], parsed["sense"], parsed["event"]), (3, "touch", "tap"))
        self.assertEqual(parsed["fields"], {"x": "540", "y": "1200"})
        self.assertEqual(parsed["text"], "Screen tapped")
        self.assertFalse(parsed["self_caused"])

    def test_rejects_bad_input(self):
        bad = [(10, "wifi", "x", None, ""), (-1, "wifi", "x", None, ""),
               (1, "Wi-Fi", "x", None, ""), (1, "wifi", "Link Down", None, ""),
               (1, "wifi", "x", {"k": "has space"}, ""), (1, "wifi", "x", {"k": 'q"'}, ""),
               (1, "wifi", "x", {f"k{i}": 1 for i in range(9)}, ""),
               (1, "w" * 25, "x", None, ""), (1, "wifi", "e" * 49, None, "")]
        for args in bad:
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.s.format_line(*args)

    def test_length_bounded_by_emitter(self):
        line = self.s.format_line(2, "mic", "speech.heard", None, "x" * 2000)
        self.assertLessEqual(len(line.encode("utf-8")), 512)
        line = self.s.format_line(2, "mic", "speech.heard", None, "ж" * 400)
        self.assertLessEqual(len(line.encode("utf-8")), 512)
        line.encode("utf-8").decode("utf-8")  # truncation never splits a character

    def test_non_sense_lines_are_ignored(self):
        for line in ("kernel: usb 1-1: new device", "NOOBIA", "NOOBIA PX wifi up",
                     "noobia P1 wifi up", ""):
            with self.subTest(line=line):
                self.assertIsNone(self.s.parse_line(line))

    def test_self_caused_flag(self):
        line = self.s.format_line(2, "agent", "job.done", {"cause": "self"}, "done")
        self.assertTrue(self.s.parse_line(line)["self_caused"])

    def test_syslog_prefix_is_tolerated(self):
        raw = "Nov 21 14:00:00 lynx user.notice noobia-sense: NOOBIA P1 wifi link.up ssid=Noobia"
        self.assertEqual(self.s.parse_line(raw)["event"], "link.up")


class TriggerContract(unittest.TestCase):
    def setUp(self):
        self.s = need("sense")
        self.t = need("trigger")

    def line(self, p, sense="wifi", event="x", **fields):
        return self.s.format_line(p, sense, event, fields or None, "")

    def test_p1_closes_immediately(self):
        c = self.t.Chunker()
        self.assertEqual(c.feed(self.line(0), 0.0), [])
        chunks = c.feed(self.line(1), 1.0)
        self.assertEqual(len(chunks), 1)
        self.assertEqual([x["p"] for x in chunks[0]], [0, 1])

    def test_pn_closes_after_n_of_that_priority(self):
        c = self.t.Chunker()
        for i in range(4):
            self.assertEqual(c.feed(self.line(5), float(i)), [], i)
        self.assertEqual(c.feed(self.line(3), 4.0), [])
        chunks = c.feed(self.line(5), 5.0)  # fifth P5
        self.assertEqual(len(chunks), 1)
        self.assertEqual(len(chunks[0]), 6)

    def test_p0_never_triggers_by_count(self):
        c = self.t.Chunker(max_lines=1000)
        for i in range(100):
            self.assertEqual(c.feed(self.line(0), float(i) * 0.1), [])

    def test_more_than_15_lines_closes(self):
        c = self.t.Chunker()
        closed = []
        for i in range(16):
            closed += c.feed(self.line(0), float(i) * 0.1)
        self.assertEqual(len(closed), 1)
        self.assertEqual(len(closed[0]), 16)

    def test_60_seconds_closes_non_empty_chunk(self):
        c = self.t.Chunker()
        c.feed(self.line(0), 0.0)
        self.assertEqual(c.tick(59.0), [])
        self.assertEqual(len(c.tick(60.0)), 1)
        self.assertEqual(c.tick(200.0), [])  # empty chunks never close

    def test_self_caused_lines_never_trigger(self):
        c = self.t.Chunker()
        for i in range(30):
            out = c.feed(self.line(1, "agent", "job.done", cause="self"), float(i) * 0.1)
            self.assertEqual(out, [])
        # they stay as context when something real closes the chunk
        chunks = c.feed(self.line(1), 4.0)
        self.assertTrue(any(x["self_caused"] for x in chunks[0]))

    def test_chunk_size_bounded(self):
        c = self.t.Chunker(max_lines=10_000, max_chunk_lines=200)
        closed = []
        for i in range(500):
            closed += c.feed(self.line(0), float(i) * 0.01)
        self.assertTrue(all(len(ch) <= 200 for ch in closed))

    def test_kill_switch_delivers_nothing(self):
        c = self.t.Chunker(disabled=lambda: True)
        self.assertEqual(c.feed(self.line(1), 0.0), [])
        self.assertEqual(c.tick(1000.0), [])

    def test_non_sense_lines_are_ignored(self):
        c = self.t.Chunker()
        self.assertEqual(c.feed("kernel: random noise", 0.0), [])
        self.assertEqual(c.tick(100.0), [])


class RankerContract(unittest.TestCase):
    CORPUS = ["NOOBIA P1 wifi link.down ssid=Noobia | Noobia Wi-Fi dropped",
              "NOOBIA P3 touch tap x=1 y=2 | Screen tapped",
              "NOOBIA P0 battery level pct=71 | Battery 71%"]

    def setUp(self):
        self.s = need("sense")
        self.r = need("ranker")

    def pattern(self, pid="cat", regex=r"^NOOBIA P1 camera object\.seen label=cat\b",
                cooldown=300, to_noob=True):
        return {"id": pid, "regex": regex, "sense": "camera", "event": "object.seen",
                "message": "A cat appeared", "to_noob": to_noob, "cooldown_s": cooldown,
                "hits": 0, "last_hit": None, "origin": "human"}

    def cat(self):
        return self.s.parse_line(self.s.format_line(1, "camera", "object.seen",
                                                    {"label": "cat", "conf": "0.91"}, "cat"))

    def test_validate_rejects_unsafe_and_wrong_patterns(self):
        example = "NOOBIA P1 camera object.seen label=cat conf=0.9"
        for regex in (r"(a+)+$", r"(\w+)\1", "x" * 201, r"^NOOBIA P1 camera object\.seen label=dog",
                      r"NOOBIA"):  # last one also matches the corpus
            with self.subTest(regex=regex), self.assertRaises(ValueError):
                self.r.validate_pattern(regex, example, self.CORPUS)
        self.r.validate_pattern(r"^NOOBIA P1 camera object\.seen label=cat\b", example, self.CORPUS)

    def test_explained_vs_unexplained(self):
        rk = self.r.Ranker([self.pattern()])
        wifi = self.s.parse_line(self.CORPUS[0])
        out = rk.process([self.cat(), wifi], 0.0)
        self.assertEqual([pid for _, pid in out["explained"]], ["cat"])
        self.assertEqual(out["unexplained"], [wifi])
        self.assertEqual(out["messages"], ["A cat appeared"])

    def test_cooldown_suppresses_repeats(self):
        rk = self.r.Ranker([self.pattern(cooldown=300)])
        self.assertEqual(rk.process([self.cat()] * 1000, 0.0)["messages"], ["A cat appeared"])
        self.assertEqual(rk.process([self.cat()], 100.0)["messages"], [])
        self.assertEqual(rk.process([self.cat()], 301.0)["messages"], ["A cat appeared"])

    def test_routine_patterns_absorb_without_message(self):
        rk = self.r.Ranker([self.pattern(to_noob=False)])
        out = rk.process([self.cat()], 0.0)
        self.assertEqual((len(out["explained"]), out["messages"], out["unexplained"]), (1, [], []))

    def test_capacity_and_archive(self):
        pats = [dict(self.pattern(f"p{i}", rf"^NOOBIA P1 camera object\.seen label=x{i}\b"))
                for i in range(101)]
        rk = self.r.Ranker(pats, capacity=100)
        self.assertLessEqual(len(rk.patterns), 100)
        self.assertEqual(len(rk.patterns) + len(rk.archive), 101)

    def test_ranks_follow_hits(self):
        rk = self.r.Ranker([self.pattern("dog", r"^NOOBIA P1 camera object\.seen label=dog\b"),
                            self.pattern("cat")])
        rk.process([self.cat()] * 3, 0.0)
        self.assertEqual(rk.patterns[0]["id"], "cat")


if __name__ == "__main__":
    unittest.main()
