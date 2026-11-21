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

    def test_kernel_timestamp_repeat_collapse(self):
        p = Prioritizer(allowlist={"kernel"}, repeat_window_s=60.0)
        line1 = "[ 1234.567890][T1234] [ESD]check doze mode=0"
        line2 = "[ 1239.123456][T1234] [ESD]check doze mode=0"
        line3 = "[ 1244.999999][T5678] [ESD]check doze mode=0"

        # First line emits
        r1 = p.process_line("kernel", line1, 0.0)
        self.assertIsNotNone(r1)
        self.assertTrue(r1.startswith("NOOBIA P0 raw line src=kernel"))

        # Subsequent lines with different uptime timestamps within 60s collapse
        r2 = p.process_line("kernel", line2, 5.0)
        self.assertIsNone(r2)

        r3 = p.process_line("kernel", line3, 10.0)
        self.assertIsNone(r3)

        # After window passes (65s), it emits again
        r4 = p.process_line("kernel", line3, 65.0)
        self.assertIsNotNone(r4)

    def test_drop_rule_action(self):
        drop_rule = {
            "id": "drop-esd",
            "source": "kernel",
            "match": {"text_contains": ["[ESD]check doze mode"]},
            "emit": {"action": "drop"},
            "examples": {
                "must": ["[ESD]check doze mode=0"],
                "must_not": ["[ESD]check active mode=1"],
            },
            "hits": 0,
            "origin": "aigel",
        }
        validate_rule(drop_rule)

        p = Prioritizer(rules=[drop_rule], allowlist={"kernel"})

        # Matching line is suppressed completely (not even P0 raw)
        res = p.process_line("kernel", "[ 1234.567890] [ESD]check doze mode=0", 0.0)
        self.assertIsNone(res)
        self.assertEqual(drop_rule["hits"], 1)

        # Non-matching line from kernel still emits P0 raw
        res_other = p.process_line("kernel", "[ 1234.567890] usb 1-1: new device", 1.0)
        self.assertIsNotNone(res_other)
        self.assertTrue(res_other.startswith("NOOBIA P0 raw line src=kernel"))

    def test_drop_rule_validation(self):
        # Invalid action
        bad_action = {
            "id": "bad-action",
            "source": "kernel",
            "match": {"text_contains": ["test"]},
            "emit": {"action": "ignore"},
            "examples": {"must": ["test"], "must_not": ["other"]},
            "hits": 0,
            "origin": "aigel",
        }
        with self.assertRaises(PrioritizerError):
            validate_rule(bad_action)


if __name__ == "__main__":
    unittest.main()
