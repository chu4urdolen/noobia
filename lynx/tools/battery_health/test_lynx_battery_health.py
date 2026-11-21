#!/usr/bin/env python3
"""Unit tests for Lynx Battery Fuel Gauge Lifespan & Cycle Health Evaluator."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess
import sys
import unittest

from lynx_battery_health import (
    evaluate_battery_health_state,
    PINNED_BOOT_ID,
    SOH_WARN_PCT,
    SOH_CRITICAL_PCT,
    CELL_IMBALANCE_WARN_MV,
    CELL_IMBALANCE_CRIT_MV,
)

TOOL_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = TOOL_DIR / "fixtures"


class TestLynxBatteryHealth(unittest.TestCase):
    def setUp(self) -> None:
        with open(FIXTURES_DIR / "battery-health-nominal.json", "r", encoding="utf-8") as f:
            self.nominal = json.load(f)
        with open(FIXTURES_DIR / "battery-aging-warning.json", "r", encoding="utf-8") as f:
            self.aging = json.load(f)
        with open(FIXTURES_DIR / "battery-critical-fault.json", "r", encoding="utf-8") as f:
            self.critical = json.load(f)

    def test_nominal_healthy(self) -> None:
        res = evaluate_battery_health_state(self.nominal)
        self.assertEqual(res["status"], "OK")
        self.assertEqual(res["state"], "BATTERY_HEALTHY")
        self.assertFalse(res["blockers"])
        self.assertFalse(res["warnings"])
        self.assertEqual(res["details"]["state_of_health_pct"], 98.4)
        self.assertEqual(res["details"]["cell_delta_mv"], 8.0)

    def test_aging_warning(self) -> None:
        res = evaluate_battery_health_state(self.aging)
        self.assertEqual(res["status"], "WARN")
        self.assertEqual(res["state"], "BATTERY_AGED_OR_IMBALANCED")
        self.assertFalse(res["blockers"])
        self.assertTrue(any("retention threshold" in w for w in res["warnings"]))
        self.assertTrue(any("Elevated dual-cell series imbalance" in w for w in res["warnings"]))

    def test_critical_degradation(self) -> None:
        res = evaluate_battery_health_state(self.critical)
        self.assertEqual(res["status"], "FAIL")
        self.assertEqual(res["state"], "BATTERY_DEGRADED_HAZARD")
        self.assertTrue(any("severely degraded" in b for b in res["blockers"]))
        self.assertTrue(any("Hazardous dual-cell series imbalance" in b for b in res["blockers"]))

    def test_cell_imbalance_warning(self) -> None:
        data = json.loads(json.dumps(self.nominal))
        data["gauge"]["cell1_voltage_mv"] = 4000
        data["gauge"]["cell2_voltage_mv"] = 3945  # 55 mV delta
        res = evaluate_battery_health_state(data)
        self.assertEqual(res["status"], "WARN")
        self.assertTrue(any("Elevated dual-cell series imbalance" in w for w in res["warnings"]))

    def test_cell_imbalance_critical(self) -> None:
        data = json.loads(json.dumps(self.nominal))
        data["gauge"]["cell1_voltage_mv"] = 4050
        data["gauge"]["cell2_voltage_mv"] = 3940  # 110 mV delta
        res = evaluate_battery_health_state(data)
        self.assertEqual(res["status"], "FAIL")
        self.assertTrue(any("Hazardous dual-cell series imbalance" in b for b in res["blockers"]))

    def test_boot_id_mismatch(self) -> None:
        data = json.loads(json.dumps(self.nominal))
        data["boot_id"] = "bad-boot-id"
        res = evaluate_battery_health_state(data)
        self.assertEqual(res["status"], "FAIL")
        self.assertTrue(any("Boot ID mismatch" in b for b in res["blockers"]))

    def test_high_impedance_warning(self) -> None:
        data = json.loads(json.dumps(self.nominal))
        data["gauge"]["internal_impedance_mohm"] = 120
        res = evaluate_battery_health_state(data)
        self.assertEqual(res["status"], "WARN")
        self.assertTrue(any("internal series impedance" in w for w in res["warnings"]))

    def test_cli_validate_offline(self) -> None:
        tool_script = TOOL_DIR / "lynx_battery_health.py"
        fixture_path = FIXTURES_DIR / "battery-health-nominal.json"
        cmd = [sys.executable, str(tool_script), "--validate", str(fixture_path), "--json"]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
        out = json.loads(proc.stdout)
        self.assertEqual(out["status"], "OK")
        self.assertEqual(out["state"], "BATTERY_HEALTHY")

    def test_cli_live_safety_gate(self) -> None:
        tool_script = TOOL_DIR / "lynx_battery_health.py"
        proc = subprocess.run(
            [sys.executable, str(tool_script), "--live"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("--allow-live", proc.stderr)

    def test_ast_safety_and_no_writes(self) -> None:
        source_path = TOOL_DIR / "lynx_battery_health.py"
        with open(source_path, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)

        forbidden = {"socket", "urllib", "requests", "http"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn(alias.name.split(".")[0], forbidden)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    self.assertNotIn(node.module.split(".")[0], forbidden)


if __name__ == "__main__":
    unittest.main()
