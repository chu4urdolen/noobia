#!/usr/bin/env python3
"""Unit tests for the Lynx Bluetooth cold-boot / sustained acceptance gate."""

import json
from pathlib import Path
import unittest

from lynx_bt_acceptance_gate import evaluate_bluetooth_trial

FIXTURES = Path(__file__).parent / "fixtures"


class TestLynxBluetoothAcceptanceGate(unittest.TestCase):
    def test_passing_trial_receipt(self):
        receipt = json.loads((FIXTURES / "passing-trial-receipt.json").read_text())
        verdict = evaluate_bluetooth_trial(
            receipt, reference_boot_id="old-boot-id-0000-0000-000000000000"
        )
        self.assertTrue(verdict.is_valid)
        self.assertEqual(verdict.status, "PASS")
        self.assertEqual(verdict.samples_evaluated, 3)
        self.assertEqual(len(verdict.failures), 0)
        self.assertIn("fresh_boot_id_verified", verdict.checks_passed)
        self.assertIn("zero_partition_writes_confirmed", verdict.checks_passed)
        self.assertIn("radio_powered_off_cleanly", verdict.checks_passed)

    def test_stale_boot_id(self):
        receipt = json.loads((FIXTURES / "stale-boot-receipt.json").read_text())
        # Provide the exact boot_id as reference_boot_id to trigger stale detection
        verdict = evaluate_bluetooth_trial(
            receipt, reference_boot_id="0fe847d2-44d6-4ac1-9000-2c99df1a51d8"
        )
        self.assertFalse(verdict.is_valid)
        self.assertEqual(verdict.status, "STALE_EVIDENCE")
        self.assertTrue(any("stale_boot_id" in f for f in verdict.failures))

    def test_absent_evidence(self):
        verdict = evaluate_bluetooth_trial(None)
        self.assertFalse(verdict.is_valid)
        self.assertEqual(verdict.status, "ABSENT_EVIDENCE")

        verdict_empty = evaluate_bluetooth_trial({})
        self.assertFalse(verdict_empty.is_valid)
        self.assertEqual(verdict_empty.status, "ABSENT_EVIDENCE")

    def test_health_failure(self):
        receipt = json.loads((FIXTURES / "health-failed-receipt.json").read_text())
        verdict = evaluate_bluetooth_trial(receipt)
        self.assertFalse(verdict.is_valid)
        self.assertEqual(verdict.status, "FAILED")
        self.assertTrue(any("battery_below_15_percent" in f for f in verdict.failures))

    def test_radio_unstopped_at_end(self):
        receipt = json.loads((FIXTURES / "radio-unstopped-receipt.json").read_text())
        verdict = evaluate_bluetooth_trial(receipt)
        self.assertFalse(verdict.is_valid)
        self.assertEqual(verdict.status, "FAILED")
        self.assertIn("radio_not_powered_off_at_trial_end", verdict.failures)

    def test_forbidden_partition_writes(self):
        receipt = json.loads((FIXTURES / "passing-trial-receipt.json").read_text())
        receipt["partition_writes"] = True
        verdict = evaluate_bluetooth_trial(receipt)
        self.assertFalse(verdict.is_valid)
        self.assertIn("forbidden_partition_writes_detected", verdict.failures)

    def test_forbidden_runlevel_writes(self):
        receipt = json.loads((FIXTURES / "passing-trial-receipt.json").read_text())
        receipt["runlevel_writes"] = True
        verdict = evaluate_bluetooth_trial(receipt)
        self.assertFalse(verdict.is_valid)
        self.assertIn("forbidden_runlevel_writes_detected", verdict.failures)

    def test_watchdog_remains_armed(self):
        receipt = json.loads((FIXTURES / "passing-trial-receipt.json").read_text())
        receipt["watchdog_remains_armed"] = True
        verdict = evaluate_bluetooth_trial(receipt)
        self.assertFalse(verdict.is_valid)
        self.assertIn("watchdog_remains_armed", verdict.failures)


if __name__ == "__main__":
    unittest.main()
