#!/usr/bin/env python3
"""Unit tests for the Lynx headset collector and receipt validator."""

import json
from pathlib import Path
import unittest

from lynx_headset_collector import (
    evaluate_headset_receipt,
    parse_switch_bits,
    decode_accessory_type,
    ACCESSORY_UNPLUGGED,
    ACCESSORY_HEADSET_4POLE,
    ACCESSORY_HEADPHONES_3POLE,
    ACCESSORY_LINEOUT,
    ACCESSORY_INVALID,
    SW_HEADPHONE_INSERT,
    SW_MICROPHONE_INSERT,
    SW_LINEOUT_INSERT,
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
        self.assertEqual(verdict.accessory_type, ACCESSORY_UNPLUGGED)
        self.assertFalse(verdict.routed_audio_validated)
        self.assertIn("UNPLUGGED", verdict.summary)
        self.assertIn("architectural_boundary", verdict.details)

    def test_headset_inserted_event_receipt(self):
        receipt = json.loads((FIXTURES / "headset-inserted-event-receipt.json").read_text())
        verdict = evaluate_headset_receipt(receipt)
        self.assertTrue(verdict.is_valid)
        self.assertEqual(verdict.status, "PASS_DETECTED")
        self.assertTrue(verdict.jack_detected)
        self.assertEqual(verdict.accessory_type, ACCESSORY_HEADSET_4POLE)
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
        self.assertEqual(verdict.accessory_type, ACCESSORY_HEADPHONES_3POLE)
        self.assertFalse(verdict.routed_audio_validated)
        self.assertTrue(verdict.details["switches"]["headphone"])
        self.assertFalse(verdict.details["switches"]["microphone"])

    def test_lineout_detected_receipt(self):
        receipt = json.loads((FIXTURES / "lineout-detected-receipt.json").read_text())
        verdict = evaluate_headset_receipt(receipt)
        self.assertTrue(verdict.is_valid)
        self.assertEqual(verdict.status, "PASS_DETECTED")
        self.assertTrue(verdict.jack_detected)
        self.assertEqual(verdict.accessory_type, ACCESSORY_LINEOUT)
        self.assertFalse(verdict.routed_audio_validated)
        self.assertTrue(verdict.details["switches"]["lineout"])
        self.assertFalse(verdict.details["switches"]["headphone"])
        self.assertFalse(verdict.details["switches"]["microphone"])

    def test_typec_analog_4pole_receipt(self):
        receipt = json.loads((FIXTURES / "typec-analog-4pole-receipt.json").read_text())
        verdict = evaluate_headset_receipt(receipt)
        self.assertTrue(verdict.is_valid)
        self.assertEqual(verdict.status, "PASS_DETECTED")
        self.assertTrue(verdict.jack_detected)
        self.assertEqual(verdict.accessory_type, ACCESSORY_HEADSET_4POLE)
        self.assertIn("typec_mux", verdict.details)
        self.assertEqual(verdict.details["typec_mux"]["switch_ic"], "FSA4480")
        self.assertEqual(verdict.details["typec_mux"]["hs_det_gpio"], 98)

    def test_invalid_combination_receipt(self):
        receipt = json.loads((FIXTURES / "invalid-combination-receipt.json").read_text())
        verdict = evaluate_headset_receipt(receipt)
        self.assertFalse(verdict.is_valid)
        self.assertEqual(verdict.status, "FAILED")
        self.assertEqual(verdict.accessory_type, ACCESSORY_INVALID)
        self.assertIn("invalid_switch_combination", verdict.failures)

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

    def test_decode_accessory_type(self):
        # Unplugged
        self.assertEqual(
            decode_accessory_type({"physical": False, "headphone": False, "microphone": False, "lineout": False}),
            ACCESSORY_UNPLUGGED,
        )
        # 4-pole
        self.assertEqual(
            decode_accessory_type({"physical": True, "headphone": True, "microphone": True, "lineout": False}),
            ACCESSORY_HEADSET_4POLE,
        )
        # 3-pole
        self.assertEqual(
            decode_accessory_type({"physical": True, "headphone": True, "microphone": False, "lineout": False}),
            ACCESSORY_HEADPHONES_3POLE,
        )
        # Lineout
        self.assertEqual(
            decode_accessory_type({"physical": True, "headphone": False, "microphone": False, "lineout": True}),
            ACCESSORY_LINEOUT,
        )
        # Invalid combinations
        self.assertEqual(
            decode_accessory_type({"physical": False, "headphone": True, "microphone": False, "lineout": False}),
            ACCESSORY_INVALID,
        )
        self.assertEqual(
            decode_accessory_type({"physical": True, "headphone": True, "microphone": False, "lineout": True}),
            ACCESSORY_INVALID,
        )

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

        # Add lineout (bit 6)
        mask_line = (1 << SW_LINEOUT_INSERT) | (1 << SW_JACK_PHYSICAL_INSERT)
        switches_line = parse_switch_bits(mask_line)
        self.assertTrue(switches_line["lineout"])
        self.assertTrue(switches_line["physical"])
        self.assertFalse(switches_line["headphone"])

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
