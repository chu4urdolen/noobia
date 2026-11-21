#!/usr/bin/env python3
"""Unit tests for Lynx Fast Charging & Charger Sub-PMIC Preflight Gate Tool."""

import json
from pathlib import Path
import unittest

from lynx_charger_preflight import (
    VOLTAGE_CRITICAL_LOW_MV,
    VOLTAGE_OVERVOLTAGE_MV,
    TEMP_MIN_CHARGE_C,
    TEMP_MAX_CUTOFF_C,
    TEMP_THROTTLE_FAST_C,
    evaluate_charger_state,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


class TestLynxChargerPreflight(unittest.TestCase):
    def test_fixture_safe_charging(self):
        data = json.loads((FIXTURES_DIR / "charger-safe-charging.json").read_text())
        res = evaluate_charger_state(data)
        self.assertTrue(res["is_safe"])
        self.assertEqual(res["state"], "SAFE_CHARGING")
        self.assertEqual(len(res["blockers"]), 0)
        self.assertEqual(res["telemetry"]["voltage_now_mv"], 8707)
        self.assertEqual(res["telemetry"]["capacity_percent"], 100)

    def test_fixture_overheat_blocked(self):
        data = json.loads((FIXTURES_DIR / "charger-overheat-blocked.json").read_text())
        res = evaluate_charger_state(data)
        self.assertFalse(res["is_safe"])
        self.assertEqual(res["state"], "HAZARD_BLOCKED")
        self.assertTrue(any("exceeds maximum charging cutoff" in b for b in res["blockers"]))

    def test_fixture_undervoltage_blocked(self):
        data = json.loads((FIXTURES_DIR / "charger-undervoltage-blocked.json").read_text())
        res = evaluate_charger_state(data)
        self.assertFalse(res["is_safe"])
        self.assertEqual(res["state"], "HAZARD_BLOCKED")
        self.assertTrue(any("below critical low cutoff" in b for b in res["blockers"]))

    def test_thermal_throttling_band(self):
        # 43 C while charging -> state THERMAL_THROTTLED (not blocked, but warned)
        data = {
            "boot_id": "0fe847d2-44d6-4ac1-9000-2c99df1a51d8",
            "voltage_now_mv": 8200,
            "capacity_percent": 75,
            "temp_c": 43.0,
            "status": "Charging",
            "charger_online": True,
        }
        res = evaluate_charger_state(data)
        self.assertTrue(res["is_safe"])
        self.assertEqual(res["state"], "THERMAL_THROTTLED")
        self.assertTrue(any("throttling band" in w for w in res["warnings"]))

    def test_cold_temperature_charging_blocked(self):
        # -2 C while charging -> blocked (lithium plating hazard)
        data = {
            "boot_id": "0fe847d2-44d6-4ac1-9000-2c99df1a51d8",
            "voltage_now_mv": 7600,
            "capacity_percent": 50,
            "temp_c": -2.0,
            "status": "Charging",
            "charger_online": True,
        }
        res = evaluate_charger_state(data)
        self.assertFalse(res["is_safe"])
        self.assertEqual(res["state"], "HAZARD_BLOCKED")
        self.assertTrue(any("below minimum charging threshold" in b for b in res["blockers"]))

    def test_boot_id_mismatch(self):
        data = {
            "boot_id": "stale-boot-id",
            "voltage_now_mv": 8000,
            "capacity_percent": 80,
            "temp_c": 25.0,
        }
        res = evaluate_charger_state(data)
        self.assertFalse(res["is_safe"])
        self.assertTrue(any("Boot ID mismatch" in b for b in res["blockers"]))


if __name__ == "__main__":
    unittest.main()
