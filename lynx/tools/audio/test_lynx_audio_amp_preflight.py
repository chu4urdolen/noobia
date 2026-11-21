#!/usr/bin/env python3
"""Unit tests for Lynx Audio Smart Amplifier Preflight Gate Tool."""

import json
from pathlib import Path
import unittest

from lynx_audio_amp_preflight import (
    EXPECTED_AMP_ADDRS,
    EXPECTED_I2C_BUS,
    MIN_SPEAKER_IMPEDANCE_MOHM,
    MAX_SPEAKER_IMPEDANCE_MOHM,
    PINNED_BOOT_ID,
    check_stock_firmware,
    evaluate_audio_amp_state,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


class TestLynxAudioAmpPreflight(unittest.TestCase):
    def test_check_stock_firmware(self):
        ok, blockers, details = check_stock_firmware()
        self.assertTrue(ok, f"Firmware check failed: {blockers}")
        self.assertEqual(len(blockers), 0)
        self.assertGreater(details["firmware_size"], 1000)

    def test_fixture_audio_amp_ready(self):
        data = json.loads((FIXTURES_DIR / "audio-amp-ready.json").read_text())
        res = evaluate_audio_amp_state(data)
        self.assertTrue(res["is_ready"])
        self.assertEqual(res["state"], "READY_PREFLIGHT")
        self.assertEqual(len(res["blockers"]), 0)
        self.assertTrue(res["safety"]["acoustic_safety_validated"])
        self.assertTrue(res["safety"]["audio_output_prevented"])
        self.assertEqual(res["topology"]["channels"]["left"]["device_node"], "6-0034")
        self.assertEqual(res["topology"]["channels"]["right"]["device_node"], "6-0035")

    def test_fixture_audio_amp_missing_i2c(self):
        data = json.loads((FIXTURES_DIR / "audio-amp-missing-i2c.json").read_text())
        res = evaluate_audio_amp_state(data)
        self.assertFalse(res["is_ready"])
        self.assertEqual(res["state"], "BLOCKED")
        self.assertTrue(any("Missing stereo amplifier I2C" in b for b in res["blockers"]))

    def test_fixture_audio_amp_impedance_fault(self):
        data = json.loads((FIXTURES_DIR / "audio-amp-impedance-fault.json").read_text())
        res = evaluate_audio_amp_state(data)
        self.assertFalse(res["is_ready"])
        self.assertEqual(res["state"], "BLOCKED")
        self.assertTrue(any("impedance out of nominal range" in b for b in res["blockers"]))

    def test_boot_id_mismatch(self):
        data = json.loads((FIXTURES_DIR / "audio-amp-ready.json").read_text())
        data["boot_id"] = "wrong-boot-id-uuid"
        res = evaluate_audio_amp_state(data)
        self.assertFalse(res["is_ready"])
        self.assertTrue(any("Boot ID mismatch" in b for b in res["blockers"]))

    def test_impedance_bounds(self):
        # 4999 mOhm should fail (below 5000)
        data = json.loads((FIXTURES_DIR / "audio-amp-ready.json").read_text())
        data["left_channel_impedance_mohm"] = 4999
        res = evaluate_audio_amp_state(data)
        self.assertFalse(res["is_ready"])

        # 8001 mOhm should fail (above 8000)
        data["left_channel_impedance_mohm"] = 8001
        res = evaluate_audio_amp_state(data)
        self.assertFalse(res["is_ready"])

        # 7000 mOhm should pass
        data["left_channel_impedance_mohm"] = 7000
        res = evaluate_audio_amp_state(data)
        self.assertTrue(res["is_ready"])


if __name__ == "__main__":
    unittest.main()
