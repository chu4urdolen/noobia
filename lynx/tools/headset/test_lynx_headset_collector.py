#!/usr/bin/env python3
"""Unit tests for the Lynx headset collector and receipt validator."""

import json
from pathlib import Path
import unittest

from lynx_headset_collector import (
    evaluate_headset_receipt,
    parse_switch_bits,
    SW_HEADPHONE_INSERT,
    SW_MICROPHONE_INSERT,
    SW_JACK_PHYSICAL_INSERT,
)

FIXTURES = Path(__file__).parent / "fixtures"


class TestLynxHeadsetCollector(unittest.TestCase):
    def test_unplugged_status_receipt(self):
        receipt = json.loads((FIXTURES / "unplugged-status-receipt.json").read_text())
        verdict = evaluate_headset_receipt(receipt)
        self.assertTrue(verdict.is_valid)
        self.assertEqual(verdict.status, "PASS_UNPLUGGED")
        self.assertFalse(verdict.jack_detected)
        self.assertFalse(verdict.routed_audio_validated)
        self.assertIn("UNPLUGGED", verdict.summary)
        self.assertIn("architectural_boundary", verdict.details)

    def test_headset_inserted_event_receipt(self):
        receipt = json.loads((FIXTURES / "headset-inserted-event-receipt.json").read_text())
        verdict = evaluate_headset_receipt(receipt)
        self.assertTrue(verdict.is_valid)
        self.assertEqual(verdict.status, "PASS_DETECTED")
        self.assertTrue(verdict.jack_detected)
        self.assertFalse(verdict.routed_audio_validated)
        self.assertTrue(verdict.details["switches"]["headphone"])
        self.assertTrue(verdict.details["switches"]["microphone"])
        self.assertTrue(verdict.details["switches"]["physical"])

    def test_headphones_only_receipt(self):
        receipt = json.loads((FIXTURES / "headphones-only-receipt.json").read_text())
        verdict = evaluate_headset_receipt(receipt)
        self.assertTrue(verdict.is_valid)
        self.assertEqual(verdict.status, "PASS_DETECTED")
        self.assertTrue(verdict.jack_detected)
        self.assertFalse(verdict.routed_audio_validated)
        self.assertTrue(verdict.details["switches"]["headphone"])
        self.assertFalse(verdict.details["switches"]["microphone"])

    def test_malformed_receipt(self):
        receipt = json.loads((FIXTURES / "malformed-receipt.json").read_text())
        verdict = evaluate_headset_receipt(receipt)
        self.assertFalse(verdict.is_valid)
        self.assertEqual(verdict.status, "FAILED")
        self.assertTrue(any("no_switch_state" in f for f in verdict.failures))

    def test_absent_receipt(self):
        verdict = evaluate_headset_receipt(None)
        self.assertFalse(verdict.is_valid)
        self.assertEqual(verdict.status, "ABSENT")

        verdict_empty = evaluate_headset_receipt({})
        self.assertFalse(verdict_empty.is_valid)
        self.assertEqual(verdict_empty.status, "ABSENT")

    def test_parse_switch_bits(self):
        # Bitmask with headphone (bit 2) and physical (bit 7)
        mask = (1 << SW_HEADPHONE_INSERT) | (1 << SW_JACK_PHYSICAL_INSERT)
        switches = parse_switch_bits(mask)
        self.assertTrue(switches["headphone"])
        self.assertTrue(switches["physical"])
        self.assertFalse(switches["microphone"])
        self.assertFalse(switches["lineout"])

        # Add microphone (bit 4)
        mask |= 1 << SW_MICROPHONE_INSERT
        switches_full = parse_switch_bits(mask)
        self.assertTrue(switches_full["microphone"])

    def test_strict_separation_of_jack_vs_routed_audio(self):
        receipt = json.loads((FIXTURES / "headset-inserted-event-receipt.json").read_text())
        verdict = evaluate_headset_receipt(receipt)
        self.assertFalse(
            verdict.routed_audio_validated,
            "Jack detection must NEVER mark routed audio as validated",
        )
        self.assertIn(
            "Jack switch detection validates mechanical/impedance sense only",
            verdict.details["architectural_boundary"],
        )


if __name__ == "__main__":
    unittest.main()
