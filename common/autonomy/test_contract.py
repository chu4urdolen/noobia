"""Conformance tests for the Noobia autonomy contract (ARCHITECTURE.md v0.2).

Written first (task E0) as the target for the harness. Each block skips until
its module exists; once a module lands, every test in its block must pass.
Change a test only together with ARCHITECTURE.md and a forge note.

Required interfaces
-------------------
sense.py
  format_line(p, sense, event, fields=None, text="") -> str   # ValueError on bad input
  parse_line(line) -> dict | None
      # keys: p, sense, event, fields (dict of str), text, self_caused (bool), raw

trigger.py
  Chunker(window_s=60, max_lines=15, max_chunk_lines=200, max_bytes=32768,
          carry_max_lines=200, carry_max_age_s=600,
          volume_resets_priority=True, disabled=lambda: False)
    .feed(line, now) -> list[Closed]
    .tick(now)       -> list[Closed]
    .carried         -> list[dict]          # priority lines waiting, in order
  Closed = dict(reason="priority"|"volume"|"timeout", lines=[parsed dicts])
      # `lines` is what is SENT on; a close that sends nothing is not returned

ranker.py
  validate_pattern(pattern: dict, corpus: list[str]) -> None   # ValueError if invalid
  Ranker(patterns, store_capacity=200, active_capacity=100)
    .process(lines, now) -> dict(explained=[(line, pattern_id)],
                                 unexplained=[line], messages=[str])
    .store  -> list[dict]   # ranked, <= store_capacity
    .active -> list[dict]   # top of store, <= active_capacity, used for matching
    .archive -> list[dict]  # pushed out of the store, never silently deleted
  pattern: id, match{sense, event, fields{}, text_contains}, message, to_noob,
           cooldown_s, examples{must[], must_not[]}, hits, last_hit, origin,
           optional regex

prioritizer.py
  validate_rule(rule: dict) -> None                 # ValueError if invalid
  Prioritizer(rules, sources: list[str], repeat_window_s=60, rules_capacity=200)
    .process(source: str, text: str, now: float) -> str | None   # a sense line or None
    .add_rule(rule) / .revert(rule_id) / .rules
  rule: id, source, match{text_contains: [literals]}, emit{p, sense, event},
        examples{must[], must_not[]}, origin, hits
"""

import importlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))


def need(name):
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError:
        raise unittest.SkipTest(f"{name}.py not implemented yet (contract target)")


class SenseLineContract(unittest.TestCase):
    def setUp(self):
        self.s = need("sense")

    def test_two_digit_priorities(self):
        line = self.s.format_line(15, "sms", "received", None, "You're a Noob")
        self.assertEqual(line, "NOOBIA P15 sms received | You're a Noob")
        self.assertEqual(self.s.parse_line(line)["p"], 15)
        self.assertIsNone(self.s.parse_line("NOOBIA P100 sms received"))

    def test_canonical_format(self):
        self.assertEqual(
            self.s.format_line(1, "wifi", "link.down", {"ssid": "Noobia"}, "Noobia Wi-Fi dropped"),
            "NOOBIA P1 wifi link.down ssid=Noobia | Noobia Wi-Fi dropped")
        self.assertEqual(self.s.format_line(0, "battery", "level", {"pct": 71}),
                         "NOOBIA P0 battery level pct=71")

    def test_round_trip(self):
        line = self.s.format_line(3, "touch", "tap", {"x": 540, "y": 1200}, "Screen tapped")
        d = self.s.parse_line(line)
        self.assertEqual((d["p"], d["sense"], d["event"], d["text"]), (3, "touch", "tap", "Screen tapped"))
        self.assertEqual(d["fields"], {"x": "540", "y": "1200"})
        self.assertFalse(d["self_caused"])

    def test_rejects_bad_input(self):
        bad = [(100, "wifi", "x", None), (-1, "wifi", "x", None), (1, "Wi-Fi", "x", None),
               (1, "wifi", "Link Down", None), (1, "wifi", "x", {"k": "has space"}),
               (1, "wifi", "x", {"k": 'q"'}), (1, "wifi", "x", {"k": "a|b"}),
               (1, "wifi", "x", {"K": "v"}), (1, "wifi", "x", {f"k{i}": 1 for i in range(9)}),
               (1, "w" * 25, "x", None), (1, "wifi", "e" * 49, None)]
        for args in bad:
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.s.format_line(*args)

    def test_length_bounded_on_character_boundary(self):
        for text in ("x" * 2000, "ж" * 400, "🐈" * 300):
            line = self.s.format_line(2, "mic", "speech.heard", None, text)
            raw = line.encode("utf-8")
            self.assertLessEqual(len(raw), 512)
            raw.decode("utf-8")

    def test_non_sense_lines_are_none(self):
        for line in ("kernel: usb 1-1: new device", "NOOBIA", "NOOBIA PX wifi up",
                     "noobia P1 wifi up", "", "NOOBIA P1 Wifi up"):
            with self.subTest(line=line):
                self.assertIsNone(self.s.parse_line(line))

    def test_self_caused_and_syslog_prefix(self):
        d = self.s.parse_line(self.s.format_line(2, "agent", "job.done", {"cause": "self"}))
        self.assertTrue(d["self_caused"])
        raw = "Nov 21 14:00:00 lynx user.notice noobia-sense: NOOBIA P1 wifi link.up ssid=Noobia"
        self.assertEqual(self.s.parse_line(raw)["event"], "link.up")


class TriggerContract(unittest.TestCase):
    def setUp(self):
        self.s = need("sense")
        self.t = need("trigger")

    def L(self, p, sense="wifi", event="x", **fields):
        return self.s.format_line(p, sense, event, fields or None)

    def test_p1_closes_on_priority_immediately(self):
        c = self.t.Chunker()
        self.assertEqual(c.feed(self.L(0), 0.0), [])
        (closed,) = c.feed(self.L(1), 1.0)
        self.assertEqual(closed["reason"], "priority")
        self.assertEqual([x["p"] for x in closed["lines"]], [0, 1])

    def test_pn_closes_after_n_of_that_priority(self):
        c = self.t.Chunker()
        for i in range(4):
            self.assertEqual(c.feed(self.L(5), float(i)), [])
        self.assertEqual(c.feed(self.L(3), 4.0), [])
        (closed,) = c.feed(self.L(5), 5.0)
        self.assertEqual((closed["reason"], len(closed["lines"])), ("priority", 6))

    def test_p0_never_triggers_by_priority(self):
        c = self.t.Chunker(max_lines=10_000)
        for i in range(100):
            self.assertEqual(c.feed(self.L(0), i * 0.1), [])

    def test_volume_closes_after_more_than_15(self):
        c = self.t.Chunker()
        out = []
        for i in range(16):
            out += c.feed(self.L(0), i * 0.1)
        self.assertEqual([(x["reason"], len(x["lines"])) for x in out], [("volume", 16)])

    def test_timeout_closes_non_empty_chunk(self):
        c = self.t.Chunker()
        c.feed(self.L(0), 0.0)
        self.assertEqual(c.tick(59.0), [])
        (closed,) = c.tick(60.0)
        self.assertEqual(closed["reason"], "timeout")
        self.assertEqual(c.tick(500.0), [])

    def test_timeout_strips_priority_lines_and_carries_them_in_order(self):
        """Noob's example: 10 P15 lines in a 60 s chunk, then 5 more within 5 s."""
        c = self.t.Chunker()
        for i in range(10):
            c.feed(self.L(15, event=f"e{i}"), float(i))
        c.feed(self.L(0, event="quiet"), 10.0)
        (closed,) = c.tick(60.0)
        self.assertEqual(closed["reason"], "timeout")
        self.assertEqual([x["event"] for x in closed["lines"]], ["quiet"])    # P lines stripped
        self.assertEqual([x["event"] for x in c.carried], [f"e{i}" for i in range(10)])
        out = []
        for i in range(10, 15):
            out += c.feed(self.L(15, event=f"e{i}"), 60.0 + (i - 9))           # 5 more in 5 s
        (closed,) = out
        self.assertEqual(closed["reason"], "priority")
        self.assertEqual([x["event"] for x in closed["lines"]], [f"e{i}" for i in range(15)])
        self.assertEqual(c.carried, [])

    def test_timeout_with_only_priority_lines_sends_nothing(self):
        c = self.t.Chunker()
        c.feed(self.L(5), 0.0)
        self.assertEqual(c.tick(60.0), [])
        self.assertEqual(len(c.carried), 1)

    def test_volume_sends_everything_and_resets_priority(self):
        """Noob: a 15+ line chunk goes as it is, priority lines included; counters reset."""
        c = self.t.Chunker()
        for i in range(8):
            c.feed(self.L(9, event=f"c{i}"), i * 0.1)     # 8 of 9 needed: no trigger
        self.assertEqual(c.tick(60.0), [])                # only P lines: nothing sent
        self.assertEqual(len(c.carried), 8)
        out = []
        for i in range(15):
            out += c.feed(self.L(0, event=f"n{i}"), 61.0 + i * 0.1)
        self.assertEqual(out, [])                         # carried lines don't count; 15 is not >15
        (closed,) = c.feed(self.L(0, event="n15"), 63.0)
        self.assertEqual(closed["reason"], "volume")
        self.assertEqual([x["event"] for x in closed["lines"]],
                         [f"c{i}" for i in range(8)] + [f"n{i}" for i in range(16)])
        self.assertEqual(c.carried, [])                   # priority counters reset

    def test_volume_carry_mode_is_configurable(self):
        c = self.t.Chunker(volume_resets_priority=False)
        for i in range(3):
            c.feed(self.L(9, event=f"c{i}"), i * 0.1)
        self.assertEqual(c.tick(60.0), [])                # carried into the next chunk
        out = []
        for i in range(16):
            out += c.feed(self.L(0, event=f"n{i}"), 61.0 + i * 0.1)
        (closed,) = out
        self.assertEqual(closed["reason"], "volume")
        self.assertEqual([x["event"] for x in closed["lines"]], [f"n{i}" for i in range(16)])
        self.assertEqual([x["event"] for x in c.carried], ["c0", "c1", "c2"])

    def test_max_lines_is_configurable(self):
        c = self.t.Chunker(max_lines=3)
        out = []
        for i in range(4):
            out += c.feed(self.L(0), i * 0.1)
        self.assertEqual([x["reason"] for x in out], ["volume"])

    def test_self_caused_lines_trigger_nothing_but_travel_as_context(self):
        c = self.t.Chunker()
        for i in range(30):
            self.assertEqual(c.feed(self.L(1, "agent", "job.done", cause="self"), i * 0.1), [])
        (closed,) = c.feed(self.L(1), 4.0)
        self.assertEqual(sum(1 for x in closed["lines"] if x["self_caused"]), 30)

    def test_carry_bounded_and_expired_lines_released(self):
        c = self.t.Chunker(carry_max_age_s=600)
        c.feed(self.L(9, event="old"), 0.0)
        self.assertEqual(c.tick(60.0), [])
        c.feed(self.L(0, event="later"), 700.0)
        (closed,) = c.tick(760.0)
        self.assertIn("old", [x["event"] for x in closed["lines"]])
        self.assertEqual(c.carried, [])
        c = self.t.Chunker(carry_max_lines=5, max_lines=10_000)
        for i in range(20):
            c.feed(self.L(9, event=f"x{i}"), float(i))
        c.tick(100.0)
        self.assertLessEqual(len(c.carried), 5)

    def test_chunk_size_bounded(self):
        c = self.t.Chunker(max_lines=10_000, max_chunk_lines=200)
        out = []
        for i in range(500):
            out += c.feed(self.L(0), i * 0.01)
        self.assertTrue(out)
        self.assertTrue(all(len(x["lines"]) <= 200 for x in out))

    def test_kill_switch_sends_nothing(self):
        c = self.t.Chunker(disabled=lambda: True)
        self.assertEqual(c.feed(self.L(1), 0.0), [])
        self.assertEqual(c.tick(1000.0), [])

    def test_non_sense_lines_ignored(self):
        c = self.t.Chunker()
        self.assertEqual(c.feed("kernel: random noise", 0.0), [])
        self.assertEqual(c.tick(100.0), [])


class RankerContract(unittest.TestCase):
    CORPUS = ["NOOBIA P1 wifi link.down ssid=Noobia | Noobia Wi-Fi dropped",
              "NOOBIA P5 touch tap x=1 y=2 | Screen tapped",
              "NOOBIA P0 battery level pct=71 | Battery 71%"]

    def setUp(self):
        self.s = need("sense")
        self.r = need("ranker")

    def pat(self, pid="cat-seen", label="cat", cooldown=300, to_noob=True, **extra):
        p = {"id": pid, "match": {"sense": "camera", "event": "object.seen",
                                  "fields": {"label": label}, "text_contains": None},
             "message": f"A {label} appeared in front of you", "to_noob": to_noob,
             "cooldown_s": cooldown,
             "examples": {"must": [f"NOOBIA P1 camera object.seen label={label} conf=0.9"],
                          "must_not": ["NOOBIA P1 camera object.seen label=zebra conf=0.9"]},
             "hits": 0, "last_hit": None, "origin": "human"}
        p.update(extra)
        return p

    def seen(self, label="cat"):
        return self.s.parse_line(self.s.format_line(1, "camera", "object.seen",
                                                    {"label": label, "conf": "0.91"}, label))

    def test_structured_pattern_is_valid(self):
        self.r.validate_pattern(self.pat(), self.CORPUS)

    def test_examples_are_enforced(self):
        bad = self.pat()
        bad["examples"]["must"] = ["NOOBIA P1 camera object.seen label=dog conf=0.9"]
        with self.assertRaises(ValueError):
            self.r.validate_pattern(bad, self.CORPUS)
        bad = self.pat()
        bad["examples"]["must_not"] = ["NOOBIA P1 camera object.seen label=cat conf=0.5"]
        with self.assertRaises(ValueError):
            self.r.validate_pattern(bad, self.CORPUS)

    def test_field_values_are_literals_not_regex(self):
        p = self.pat(label=".*")
        p["examples"] = {"must": ["NOOBIA P1 camera object.seen label=.* conf=0.9"],
                         "must_not": ["NOOBIA P1 camera object.seen label=cat conf=0.9"]}
        self.r.validate_pattern(p, self.CORPUS)
        rk = self.r.Ranker([p])
        self.assertEqual(rk.process([self.seen("cat")], 0.0)["explained"], [])

    def test_advanced_regex_guarded(self):
        for regex in (r"(a+)+$", r"(\w+)\1", "x" * 201, r"NOOBIA"):
            p = self.pat(regex=regex)
            with self.subTest(regex=regex), self.assertRaises(ValueError):
                self.r.validate_pattern(p, self.CORPUS)
        p = self.pat(regex=None)
        p["regex"] = r"label=cat\b"
        p["examples"]["must_not"] = []  # advanced regex needs a must_not example
        with self.assertRaises(ValueError):
            self.r.validate_pattern(p, self.CORPUS)

    def test_explained_vs_unexplained(self):
        rk = self.r.Ranker([self.pat()])
        wifi = self.s.parse_line(self.CORPUS[0])
        out = rk.process([self.seen(), wifi], 0.0)
        self.assertEqual([pid for _, pid in out["explained"]], ["cat-seen"])
        self.assertEqual(out["unexplained"], [wifi])
        self.assertEqual(out["messages"], ["A cat appeared in front of you"])

    def test_cooldown_per_pattern(self):
        rk = self.r.Ranker([self.pat(cooldown=300)])
        self.assertEqual(rk.process([self.seen()] * 1000, 0.0)["messages"],
                         ["A cat appeared in front of you"])
        self.assertEqual(rk.process([self.seen()], 100.0)["messages"], [])
        self.assertEqual(rk.process([self.seen()], 301.0)["messages"],
                         ["A cat appeared in front of you"])

    def test_routine_patterns_absorb_quietly(self):
        rk = self.r.Ranker([self.pat(to_noob=False)])
        out = rk.process([self.seen()], 0.0)
        self.assertEqual((len(out["explained"]), out["messages"], out["unexplained"]), (1, [], []))

    def test_store_and_active_capacities(self):
        pats = [self.pat(f"p{i}", f"x{i}") for i in range(250)]
        rk = self.r.Ranker(pats, store_capacity=200, active_capacity=100)
        self.assertEqual(len(rk.store), 200)
        self.assertEqual(len(rk.active), 100)
        self.assertEqual(len(rk.archive), 50)
        rk2 = self.r.Ranker(pats[:3], store_capacity=2, active_capacity=1)
        self.assertEqual((len(rk2.store), len(rk2.active), len(rk2.archive)), (2, 1, 1))

    def test_only_active_patterns_match(self):
        pats = [self.pat("busy", "dog"), self.pat("idle", "cat")]
        pats[0]["hits"] = 10
        rk = self.r.Ranker(pats, store_capacity=2, active_capacity=1)
        self.assertEqual(rk.process([self.seen("cat")], 0.0)["explained"], [])

    def test_ranks_follow_hits(self):
        rk = self.r.Ranker([self.pat("dog", "dog"), self.pat("cat", "cat")])
        rk.process([self.seen("cat")] * 3, 0.0)
        self.assertEqual(rk.store[0]["id"], "cat")


class PrioritizerContract(unittest.TestCase):
    def setUp(self):
        self.s = need("sense")
        self.pz = need("prioritizer")

    def rule(self, rid="wifi-down", **changes):
        r = {"id": rid, "source": "wpa_supplicant",
             "match": {"text_contains": ["CTRL-EVENT-DISCONNECTED"]},
             "emit": {"p": 1, "sense": "wifi", "event": "link.down"},
             "examples": {"must": ["CTRL-EVENT-DISCONNECTED bssid=aa:bb reason=3"],
                          "must_not": ["CTRL-EVENT-CONNECTED - Connection to aa:bb completed"]},
             "origin": "aigel", "hits": 0}
        r.update(changes)
        return r

    def make(self, rules=None, **kw):
        return self.pz.Prioritizer([self.rule()] if rules is None else rules,
                                   sources=["wpa_supplicant", "kernel"], **kw)

    def test_mapped_line_becomes_its_sense_line(self):
        line = self.make().process("wpa_supplicant", "CTRL-EVENT-DISCONNECTED bssid=aa:bb reason=3", 0.0)
        d = self.s.parse_line(line)
        self.assertEqual((d["p"], d["sense"], d["event"]), (1, "wifi", "link.down"))
        self.assertEqual((d["fields"]["src"], d["fields"]["rule"]), ("wpa_supplicant", "wifi-down"))
        self.assertIn("CTRL-EVENT-DISCONNECTED", d["text"])

    def test_unmapped_line_from_allowed_source_is_p0_raw(self):
        d = self.s.parse_line(self.make().process("kernel", "usb 1-1: new device", 0.0))
        self.assertEqual((d["p"], d["sense"], d["event"], d["fields"]["src"]), (0, "raw", "line", "kernel"))

    def test_sources_outside_allowlist_and_noobia_views_are_ignored(self):
        p = self.make()
        self.assertIsNone(p.process("sshd", "Accepted publickey", 0.0))
        loop = self.pz.Prioritizer([self.rule()], sources=["noobia-sense", "noobia-agent", "kernel"])
        self.assertIsNone(loop.process("noobia-sense", "NOOBIA P1 wifi link.down", 0.0))
        self.assertIsNone(loop.process("noobia-agent", "flashlight on", 0.0))

    def test_repeats_collapse_within_window(self):
        p = self.make()
        text = "CTRL-EVENT-DISCONNECTED bssid=aa:bb reason=3"
        self.assertIsNotNone(p.process("wpa_supplicant", text, 0.0))
        for i in range(1, 50):
            self.assertIsNone(p.process("wpa_supplicant", text, float(i)))
        self.assertIsNotNone(p.process("wpa_supplicant", text, 61.0))

    def test_literal_matching_all_terms(self):
        r = self.rule(match={"text_contains": ["reason=3", ".*"]},
                      examples={"must": ["x reason=3 .*"], "must_not": ["x reason=3 y"]})
        self.pz.validate_rule(r)
        p = self.make([r])
        d = self.s.parse_line(p.process("wpa_supplicant", "x reason=3 anything", 0.0))
        self.assertEqual(d["p"], 0)                       # ".*" is a literal, not regex

    def test_rule_validation(self):
        self.pz.validate_rule(self.rule())
        bad = {
            "no must": self.rule(examples={"must": [], "must_not": ["x"]}),
            "no must_not": self.rule(examples={"must": ["CTRL-EVENT-DISCONNECTED"], "must_not": []}),
            "misses must": self.rule(examples={"must": ["CTRL-EVENT-CONNECTED"], "must_not": ["y"]}),
            "hits must_not": self.rule(examples={"must": ["CTRL-EVENT-DISCONNECTED a"],
                                                 "must_not": ["CTRL-EVENT-DISCONNECTED b"]}),
            "empty match": self.rule(match={"text_contains": []}),
            "empty literal": self.rule(match={"text_contains": [""]}),
            "bad priority": self.rule(emit={"p": 100, "sense": "wifi", "event": "link.down"}),
            "bad sense": self.rule(emit={"p": 1, "sense": "Wi-Fi", "event": "link.down"}),
            "noobia source": self.rule(source="noobia-sense"),
        }
        for label, r in bad.items():
            with self.subTest(label), self.assertRaises(ValueError):
                self.pz.validate_rule(r)

    def test_invalid_rules_rejected_on_load(self):
        broken = self.rule("broken", match={"text_contains": []})
        p = self.make([self.rule(), broken])
        self.assertEqual([r["id"] for r in p.rules], ["wifi-down"])

    def test_add_and_revert(self):
        p = self.make()
        text = "CTRL-EVENT-DISCONNECTED bssid=aa:bb reason=3"
        p.add_rule(self.rule(emit={"p": 5, "sense": "wifi", "event": "link.down"}))   # Aigel retunes
        self.assertEqual(self.s.parse_line(p.process("wpa_supplicant", text, 0.0))["p"], 5)
        p.revert("wifi-down")
        self.assertEqual(self.s.parse_line(p.process("wpa_supplicant", text, 100.0))["p"], 1)
        with self.assertRaises(ValueError):
            p.add_rule(self.rule(match={"text_contains": []}))

    def test_rules_capacity(self):
        rules = [self.rule(f"r{i}", match={"text_contains": [f"T{i}"]},
                           examples={"must": [f"T{i} x"], "must_not": ["zzz"]}) for i in range(5)]
        p = self.make(rules, rules_capacity=3)
        self.assertEqual(len(p.rules), 3)
        with self.assertRaises(ValueError):
            p.add_rule(self.rule("r9", match={"text_contains": ["T9"]},
                                 examples={"must": ["T9 x"], "must_not": ["zzz"]}))


if __name__ == "__main__":
    unittest.main()
