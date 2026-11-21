#!/usr/bin/env python3
"""Unit tests for Lynx GNSS Fix-Trial Readiness evaluator."""

import json
from pathlib import Path
import subprocess
import sys
import unittest

from lynx_gnss_readiness import (
    checksum_ok,
    evaluate_gnss_readiness,
    parse_nmea_sentences,
    parse_battery_snapshot_text,
    MIN_POWER_CUTOFF_PERCENT,
    MIN_SATELLITES_REQUIRED,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


class TestLynxGnssReadiness(unittest.TestCase):
    def test_nmea_checksum_validation(self):
        valid = b"$GNGGA,013000.00,3200.0000,N,03400.0000,E,1,08,1.2,45.0,M,0.0,M,,*7C"
        self.assertTrue(checksum_ok(valid))

        corrupted = b"$GNGGA,013000.00,3200.0000,N,03400.0000,E,1,08,1.2,45.0,M,0.0,M,,*FF"
        self.assertFalse(checksum_ok(corrupted))

        missing_star = b"$GNGGA,013000.00,3200.0000,N"
        self.assertFalse(checksum_ok(missing_star))

    def test_parse_nmea_sentences(self):
        sentences = [
            "$GNGGA,013000.00,3200.0000,N,03400.0000,E,1,08,1.2,45.0,M,0.0,M,,*7C",
            "$GNRMC,013000.00,A,3200.0000,N,03400.0000,E,0.05,0.0,211126,,,A*76",
            "$GPGSV,2,1,08,01,40,080,36,02,30,120,34,03,20,180,32,04,15,240,30*73",
            "$GPGSV,2,2,08,05,50,060,38,06,25,140,33,07,35,210,35,08,10,300,29*7D",
        ]
        summary = parse_nmea_sentences(sentences)
        self.assertEqual(summary["total_sentences"], 4)
        self.assertEqual(summary["valid_checksums"], 4)
        self.assertEqual(summary["fix_quality"], 1)
        self.assertEqual(summary["satellites_used"], 8)
        self.assertEqual(summary["satellites_in_view"], 8)
        self.assertEqual(summary["hdop"], 1.2)
        self.assertTrue(summary["rmc_valid"])
        self.assertEqual(summary["max_cno_dbhz"], 38.0)

    def test_parse_battery_snapshot_text(self):
        text = """gauge_device_type=42495
pack_voltage_mv=8707
capacity_percent=100
capacity_error=0
"""
        parsed = parse_battery_snapshot_text(text)
        self.assertEqual(parsed["gauge_device_type"], 42495)
        self.assertEqual(parsed["pack_voltage_mv"], 8707)
        self.assertEqual(parsed["capacity_percent"], 100)
        self.assertEqual(parsed["capacity_error"], 0)

    def test_fixture_quiescent_safe(self):
        path = FIXTURES_DIR / "gnss-readiness-quiescent.json"
        data = json.loads(path.read_text())
        verdict = evaluate_gnss_readiness(data)

        self.assertTrue(verdict.is_valid)
        self.assertEqual(verdict.status, "QUIESCENT_SAFE")
        self.assertTrue(verdict.power_gate_passed)
        self.assertTrue(verdict.driver_gate_passed)
        self.assertEqual(verdict.battery_level_percent, 100)
        self.assertIn("quiescent state", verdict.summary)

    def test_fixture_ready_for_trial(self):
        path = FIXTURES_DIR / "gnss-readiness-ready.json"
        data = json.loads(path.read_text())
        verdict = evaluate_gnss_readiness(data)

        self.assertTrue(verdict.is_valid)
        self.assertEqual(verdict.status, "READY_FOR_TRIAL")
        self.assertTrue(verdict.power_gate_passed)
        self.assertTrue(verdict.driver_gate_passed)
        self.assertTrue(verdict.sky_view_gate_passed)
        self.assertTrue(verdict.has_valid_fix)
        self.assertGreaterEqual(verdict.satellites_detected, MIN_SATELLITES_REQUIRED)
        self.assertIn("GNSS fix trial ready", verdict.summary)

    def test_fixture_low_battery_rejected(self):
        path = FIXTURES_DIR / "gnss-readiness-low-battery.json"
        data = json.loads(path.read_text())
        verdict = evaluate_gnss_readiness(data)

        self.assertFalse(verdict.is_valid)
        self.assertEqual(verdict.status, "POWER_GATE_FAIL")
        self.assertFalse(verdict.power_gate_passed)
        self.assertIn(f"battery_capacity_14_below_cutoff_{MIN_POWER_CUTOFF_PERCENT}", verdict.failures)

    def test_fixture_obstructed_sky_rejected(self):
        path = FIXTURES_DIR / "gnss-readiness-obstructed-sky.json"
        data = json.loads(path.read_text())
        verdict = evaluate_gnss_readiness(data)

        self.assertFalse(verdict.is_valid)
        self.assertEqual(verdict.status, "SKY_VIEW_OBSTRUCTED")
        self.assertTrue(verdict.power_gate_passed)
        self.assertFalse(verdict.sky_view_gate_passed)
        self.assertIn("insufficient_satellites_detected_2_min_4", verdict.failures)

    def test_cli_live_safety_gate(self):
        tool = Path(__file__).resolve().parent / "lynx_gnss_readiness.py"
        res = subprocess.run([sys.executable, str(tool), "--live"], capture_output=True, text=True)
        self.assertEqual(res.returncode, 2)
        self.assertIn("Refusing live query without both --live and --allow-live", res.stderr)


if __name__ == "__main__":
    unittest.main()
