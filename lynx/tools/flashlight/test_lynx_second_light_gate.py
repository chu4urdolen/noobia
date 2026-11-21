#!/usr/bin/env python3
"""Unit tests for the Lynx second rear light topology parser and gate."""

import json
from pathlib import Path
import unittest

from lynx_second_light_gate import evaluate_flashlight_topology

FIXTURES = Path(__file__).parent / "fixtures"


class TestLynxSecondLightGate(unittest.TestCase):
    def test_lynx_22823_single_channel_dt(self):
        dt_data = json.loads((FIXTURES / "lynx-22823-flashlight-dt.json").read_text())
        verdict = evaluate_flashlight_topology(dt_data)
        self.assertTrue(verdict.is_valid)
        self.assertEqual(verdict.status, "SINGLE_CHANNEL_ONLY")
        self.assertFalse(verdict.second_channel_exists)
        self.assertEqual(len(verdict.channels_found), 1)
        ch0 = verdict.channels_found[0]
        self.assertEqual(ch0["reg"], 0)
        self.assertEqual(ch0["type_id"], 0)
        self.assertEqual(ch0["ct_id"], 0)
        self.assertEqual(ch0["part_id"], 0)
        self.assertIn("PROVEN ABSENT", verdict.summary)

    def test_synthetic_dual_channel_dt(self):
        dt_data = json.loads((FIXTURES / "synthetic-dual-channel-dt.json").read_text())
        verdict = evaluate_flashlight_topology(dt_data)
        self.assertTrue(verdict.is_valid)
        self.assertEqual(verdict.status, "DUAL_CHANNEL_FOUND")
        self.assertTrue(verdict.second_channel_exists)
        self.assertEqual(len(verdict.channels_found), 2)

    def test_malformed_dt(self):
        dt_data = json.loads((FIXTURES / "malformed-flashlight-dt.json").read_text())
        verdict = evaluate_flashlight_topology(dt_data)
        self.assertFalse(verdict.is_valid)
        self.assertEqual(verdict.status, "MALFORMED_DT")
        self.assertTrue(len(verdict.failures) > 0)

    def test_absent_dt(self):
        verdict = evaluate_flashlight_topology(None)
        self.assertFalse(verdict.is_valid)
        self.assertEqual(verdict.status, "ABSENT")

        verdict_empty = evaluate_flashlight_topology({})
        self.assertFalse(verdict_empty.is_valid)
        self.assertEqual(verdict_empty.status, "ABSENT")

    def test_source_citations_present(self):
        dt_data = json.loads((FIXTURES / "lynx-22823-flashlight-dt.json").read_text())
        verdict = evaluate_flashlight_topology(dt_data)
        self.assertTrue(len(verdict.source_citations) >= 3)
        self.assertTrue(
            any("cust_mt6983_vitamin_camera_v4l2.dtsi" in c for c in verdict.source_citations)
        )
        self.assertTrue(any("flashlights-lm3642.c" in c for c in verdict.source_citations))


if __name__ == "__main__":
    unittest.main()
