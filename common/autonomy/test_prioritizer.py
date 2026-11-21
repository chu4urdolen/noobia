"""Unit tests for the Prioritizer (task E8)."""

import json
from pathlib import Path
import tempfile
import unittest

from prioritizer import Prioritizer, PrioritizerError, validate_rule


class TestPrioritizer(unittest.TestCase):
    def sample_rule(self, **kwargs):
        r = {
            "id": "wifi-down",
            "source": "wpa_supplicant",
            "match": {"text_contains": ["CTRL-EVENT-DISCONNECTED"]},
            "emit": {"p": 1, "sense": "wifi", "event": "link.down"},
            "examples": {
                "must": ["CTRL-EVENT-DISCONNECTED bssid=aa:bb reason=3"],
                "must_not": ["CTRL-EVENT-CONNECTED - Connection to aa:bb completed"],
            },
            "hits": 0,
            "origin": "aigel",
        }
        r.update(kwargs)
        return r

    def test_rule_validation(self):
        validate_rule(self.sample_rule())

        # Loop guard violation
        bad = self.sample_rule(source="noobia-sense")
        with self.assertRaises(PrioritizerError):
            validate_rule(bad)

        # Missing must example
        bad_ex = self.sample_rule()
        bad_ex["examples"]["must"] = []
        with self.assertRaises(PrioritizerError):
            validate_rule(bad_ex)

    def test_mapped_line_emits_rule_priority(self):
        p = Prioritizer(rules=[self.sample_rule()], allowlist={"wpa_supplicant"})
        res = p.process_line("wpa_supplicant", "CTRL-EVENT-DISCONNECTED bssid=aa:bb reason=3", 0.0)
        self.assertIsNotNone(res)
        self.assertTrue(res.startswith("NOOBIA P1 wifi link.down src=wpa_supplicant rule=wifi-down"))

    def test_unmapped_line_emits_p0_raw(self):
        p = Prioritizer(rules=[self.sample_rule()], allowlist={"wpa_supplicant"})
        res = p.process_line("wpa_supplicant", "random operational log message", 0.0)
        self.assertIsNotNone(res)
        self.assertTrue(res.startswith("NOOBIA P0 raw line src=wpa_supplicant"))

    def test_repeat_collapse(self):
        p = Prioritizer(rules=[self.sample_rule()], allowlist={"wpa_supplicant"}, repeat_window_s=60.0)
        line = "CTRL-EVENT-DISCONNECTED bssid=aa:bb reason=3"
        first = p.process_line("wpa_supplicant", line, 0.0)
        self.assertIsNotNone(first)

        # Repeated within 60s should be collapsed (None)
        second = p.process_line("wpa_supplicant", line, 10.0)
        self.assertIsNone(second)

        # After repeat_window_s, emits again
        third = p.process_line("wpa_supplicant", line, 65.0)
        self.assertIsNotNone(third)

    def test_loop_guard_rejects_noobia_sources(self):
        p = Prioritizer(allowlist={"noobia-sense", "noobia-agent", "wpa_supplicant"})
        self.assertIsNone(p.process_line("noobia-sense", "NOOBIA P1 wifi up", 0.0))
        self.assertIsNone(p.process_line("noobia-agent", "Lynx buzz", 0.0))

    def test_rule_add_and_revert(self):
        p = Prioritizer(allowlist={"wpa_supplicant"})
        rule = self.sample_rule(id="rule1")
        p.add_rule(rule)
        self.assertEqual(len(p.rules), 1)

        # Update rule
        rule_v2 = self.sample_rule(id="rule1")
        rule_v2["emit"]["p"] = 5
        p.add_rule(rule_v2)
        self.assertEqual(p.rules[0]["emit"]["p"], 5)

        # Revert
        reverted = p.revert_rule("rule1")
        self.assertTrue(reverted)
        self.assertEqual(p.rules[0]["emit"]["p"], 1)

    def test_atomic_persistence(self):
        with tempfile.NamedTemporaryFile("w+", encoding="utf-8", delete=False) as tf:
            path = tf.name

        try:
            p = Prioritizer(rules=[self.sample_rule()], allowlist={"wpa_supplicant"})
            p.save_map(path)

            loaded = Prioritizer.load_map(path, allowlist={"wpa_supplicant"})
            self.assertEqual(len(loaded.rules), 1)
            self.assertEqual(loaded.rules[0]["id"], "wifi-down")
        finally:
            Path(path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
