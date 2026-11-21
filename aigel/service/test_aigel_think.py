#!/usr/bin/env python3
"""Offline tests for Aigel's thinking step (A2 + A6 hooks).

Every LLM call is faked; nothing touches the network. Run with:

    cd /noobia && python3 -m unittest discover -s aigel/service -p 'test_aigel_think.py' -v
"""

from __future__ import annotations

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from aigel_think import (  # noqa: E402
    AigelThinker,
    QwenError,
    SYSTEM_PROMPT,
    validate_pattern,
    validate_priority_rule,
)


class FakeLLM:
    """Returns canned replies in order; raises if a reply is an Exception."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def chat(self, messages, max_tokens=1024):
        self.calls.append([m["content"] for m in messages])
        if not self.replies:
            raise QwenError("fake: out of replies")
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def reply(decision="quiet", message=None, patterns=None, rules=None, note="n"):
    return json.dumps({
        "decision": decision, "message": message,
        "patterns": patterns or [], "priority_rules": rules or [], "note": note,
    })


def good_pattern(label="cat"):
    return {
        "id": f"{label}-seen",
        "match": {"sense": "camera", "event": "object.seen",
                  "fields": {"label": label}},
        "message": f"A {label} appeared",
        "to_noob": True,
        "cooldown_s": 300,
        "examples": {
            "must": [f"NOOBIA P1 camera object.seen label={label} conf=0.9"],
            "must_not": [f"NOOBIA P1 camera object.seen label=dog conf=0.9"],
        },
    }


def good_rule():
    return {
        "id": "wifi-down",
        "source": "wpa_supplicant",
        "match": {"text_contains": ["CTRL-EVENT-DISCONNECTED"]},
        "emit": {"p": 1, "sense": "wifi", "event": "link.down"},
        "examples": {
            "must": ["CTRL-EVENT-DISCONNECTED bssid=aa:bb reason=3"],
            "must_not": ["CTRL-EVENT-CONNECTED - Connection completed"],
        },
    }


class ThinkerShapeTests(unittest.TestCase):
    def test_quiet_passthrough(self):
        t = AigelThinker(llm=FakeLLM([reply()]))
        d = t.decide("lynx", "TIMEOUT", ["NOOBIA P0 wifi rssi level=-65"])
        self.assertEqual(d["decision"], "quiet")
        self.assertIsNone(d["message"])
        self.assertEqual(d["note"], "n")

    def test_message_kept(self):
        t = AigelThinker(llm=FakeLLM([reply("message", "A cat appeared in front of you")]))
        d = t.decide("lynx", "PRIORITY", ["NOOBIA P1 camera object.seen label=cat"])
        self.assertEqual(d["decision"], "message")
        self.assertEqual(d["message"], "A cat appeared in front of you")

    def test_message_without_text_becomes_quiet(self):
        t = AigelThinker(llm=FakeLLM([reply("message", "")]))
        d = t.decide("lynx", "PRIORITY", ["x"])
        self.assertEqual(d["decision"], "quiet")
        self.assertIsNone(d["message"])
        self.assertIn("dropped", d["note"])

    def test_unknown_decision_becomes_quiet(self):
        t = AigelThinker(llm=FakeLLM([reply("yell")]))
        d = t.decide("lynx", "PRIORITY", ["x"])
        self.assertEqual(d["decision"], "quiet")

    def test_message_capped_at_500(self):
        t = AigelThinker(llm=FakeLLM([reply("message", "x" * 900)]))
        d = t.decide("lynx", "PRIORITY", ["x"])
        self.assertEqual(len(d["message"]), 500)

    def test_json_hidden_in_prose_is_found(self):
        t = AigelThinker(llm=FakeLLM(["Sure, here is my answer: " + reply() + " (as promised)"]))
        d = t.decide("lynx", "TIMEOUT", ["x"])
        self.assertEqual(d["decision"], "quiet")

    def test_code_fenced_json_is_found(self):
        t = AigelThinker(llm=FakeLLM(["```json\n" + reply() + "\n```"]))
        self.assertEqual(t.decide("lynx", "TIMEOUT", ["x"])["decision"], "quiet")

    def test_malformed_json_retries_once_then_quiet(self):
        llm = FakeLLM(["no json here", "still none"])
        t = AigelThinker(llm=llm)
        d = t.decide("lynx", "TIMEOUT", ["x"])
        self.assertEqual(d["decision"], "quiet")
        self.assertIn("unavailable", d["note"])
        self.assertEqual(len(llm.calls), 2)
        self.assertIn("Reply with JSON only", llm.calls[1][-1])

    def test_one_bad_then_good_json_succeeds(self):
        llm = FakeLLM(["oops", reply("message", "she is back")])
        d = AigelThinker(llm=llm).decide("lynx", "TIMEOUT", ["x"])
        self.assertEqual((d["decision"], d["message"]), ("message", "she is back"))

    def test_llm_down_is_honest_quiet(self):
        t = AigelThinker(llm=FakeLLM([QwenError("ollama unreachable")]))
        d = t.decide("lynx", "TIMEOUT", ["x"])
        self.assertEqual(d["decision"], "quiet")
        self.assertIn("unavailable", d["note"])
        self.assertIn("ollama unreachable", d["note"])

    def test_prompt_carries_personality_and_guardrail(self):
        llm = FakeLLM([reply()])
        AigelThinker(llm=llm).decide("lynx", "TIMEOUT", ["x"])
        system = llm.calls[0][0]
        self.assertIn("Aigel", system)
        self.assertIn("nurse angel", system)
        self.assertIn("never command hardware", system)
        self.assertIn("unsolved mystery", system)
        user = json.loads(llm.calls[0][1])
        self.assertEqual((user["host"], user["chunk_reason"]), ("lynx", "TIMEOUT"))

    def test_lines_are_bounded_to_200_strings(self):
        llm = FakeLLM([reply()])
        t = AigelThinker(llm=llm)
        t.decide("lynx", "VOLUME", [f"line {i}" for i in range(500)] + [42])
        user = json.loads(llm.calls[0][1])
        self.assertEqual(len(user["lines"]), 200)


class PatternValidationTests(unittest.TestCase):
    def test_valid_pattern_survives(self):
        d = AigelThinker(llm=FakeLLM([reply(patterns=[good_pattern()])])).decide("lynx", "PRIORITY", ["x"])
        self.assertEqual(len(d["patterns"]), 1)
        p = d["patterns"][0]
        self.assertEqual(p["match"]["sense"], "camera")
        self.assertEqual(p["origin"], "aigel")

    def test_pattern_without_event_is_dropped(self):
        pat = good_pattern()
        del pat["match"]["event"]
        d = AigelThinker(llm=FakeLLM([reply(patterns=[pat])])).decide("lynx", "PRIORITY", ["x"])
        self.assertEqual(d["patterns"], [])
        self.assertIn("pattern", d["note"])

    def test_pattern_without_sense_is_dropped(self):
        pat = good_pattern()
        del pat["match"]["sense"]
        self.assertIsNone(validate_pattern(pat))

    def test_pattern_with_regex_is_dropped(self):
        pat = good_pattern()
        pat["regex"] = "cat.*"
        self.assertIsNone(validate_pattern(pat))
        pat2 = good_pattern()
        pat2["match"]["regex"] = ".*"
        self.assertIsNone(validate_pattern(pat2))

    def test_pattern_without_must_examples_is_dropped(self):
        pat = good_pattern()
        pat["examples"] = {"must": [], "must_not": ["x"]}
        self.assertIsNone(validate_pattern(pat))

    def test_max_two_patterns_kept(self):
        pats = [good_pattern(label) for label in ("cat", "dog", "fox")]
        d = AigelThinker(llm=FakeLLM([reply(patterns=pats)])).decide("lynx", "PRIORITY", ["x"])
        self.assertEqual([p["id"] for p in d["patterns"]], ["cat-seen", "dog-seen"])

    def test_pattern_field_limited_to_8(self):
        pat = good_pattern()
        pat["match"]["fields"] = {f"k{i}": "v" for i in range(12)}
        self.assertIsNone(validate_pattern(pat))


class PriorityRuleValidationTests(unittest.TestCase):
    def test_valid_rule_survives_with_aigel_origin(self):
        r = good_rule()
        d = AigelThinker(llm=FakeLLM([reply(rules=[r])])).decide("lynx", "TIMEOUT", ["x"])
        self.assertEqual(len(d["priority_rules"]), 1)
        out = d["priority_rules"][0]
        self.assertEqual(out["origin"], "aigel")
        self.assertEqual(out["hits"], 0)
        self.assertEqual(out["emit"]["p"], 1)

    def test_rule_examples_must_contain_terms(self):
        r = good_rule()
        r["examples"] = {"must": ["unrelated line"], "must_not": ["CTRL-EVENT-CONNECTED x"]}
        self.assertIsNone(validate_priority_rule(r))

    def test_rule_must_not_must_not_match(self):
        r = good_rule()
        r["examples"]["must_not"] = ["CTRL-EVENT-DISCONNECTED other"]
        self.assertIsNone(validate_priority_rule(r))

    def test_rule_p0_is_dropped(self):
        r = good_rule()
        r["emit"]["p"] = 0
        self.assertIsNone(validate_priority_rule(r))

    def test_rule_p100_is_dropped(self):
        r = good_rule()
        r["emit"]["p"] = 100
        self.assertIsNone(validate_priority_rule(r))

    def test_rule_bad_sense_is_dropped(self):
        r = good_rule()
        r["emit"]["sense"] = "Wi-Fi"
        self.assertIsNone(validate_priority_rule(r))

    def test_rule_noobia_source_is_dropped(self):
        r = good_rule()
        r["source"] = "noobia-agent"
        self.assertIsNone(validate_priority_rule(r))

    def test_rule_empty_terms_is_dropped(self):
        r = good_rule()
        r["match"] = {"text_contains": []}
        self.assertIsNone(validate_priority_rule(r))

    def test_rule_needs_both_example_sides(self):
        r = good_rule()
        r["examples"] = {"must": ["CTRL-EVENT-DISCONNECTED x"], "must_not": []}
        self.assertIsNone(validate_priority_rule(r))

    def test_max_two_rules_kept(self):
        rules = []
        for i in range(4):
            r = good_rule()
            r["id"] = f"r{i}"
            r["match"] = {"text_contains": [f"T{i}"]}
            r["examples"] = {"must": [f"T{i} line"], "must_not": [f"zzz{i} other"]}
            rules.append(r)
        d = AigelThinker(llm=FakeLLM([reply(rules=rules)])).decide("lynx", "TIMEOUT", ["x"])
        self.assertEqual([r["id"] for r in d["priority_rules"]], ["r0", "r1"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
