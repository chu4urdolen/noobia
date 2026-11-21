#!/usr/bin/env python3
"""Unit tests for Lynx Thermal Mitigation Zones & Trip Points Validator."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess
import sys
import unittest

from lynx_thermal_zones_validator import (
    evaluate_thermal_zones_state,
    PINNED_BOOT_ID,
    TRIP_SOC_CRITICAL_MC,
    TRIP_SKIN_PASSIVE_MC,
    TRIP_SKIN_CRIT_MC,
)

TOOL_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = TOOL_DIR / "fixtures"


class TestLynxThermalZonesValidator(unittest.TestCase):
    def setUp(self) -> None:
        with open(FIXTURES_DIR / "thermal-nominal-quiescent.json", "r", encoding="utf-8") as f:
            self.nominal = json.load(f)
        with open(FIXTURES_DIR / "thermal-throttled-passive.json", "r", encoding="utf-8") as f:
            self.throttled = json.load(f)
        with open(FIXTURES_DIR / "thermal-critical-trip.json", "r", encoding="utf-8") as f:
            self.critical = json.load(f)

    def test_nominal_quiescent(self) -> None:
        res = evaluate_thermal_zones_state(self.nominal)
        self.assertEqual(res["status"], "OK")
        self.assertEqual(res["state"], "THERMAL_ENVELOPE_NOMINAL")
        self.assertFalse(res["blockers"])
        self.assertFalse(res["warnings"])
        self.assertEqual(res["details"]["soc_max"]["temp_c"], 41.5)
        self.assertEqual(res["details"]["skin_ntc"]["temp_c"], 33.2)

    def test_throttled_passive(self) -> None:
        res = evaluate_thermal_zones_state(self.throttled)
        self.assertEqual(res["status"], "WARN")
        self.assertEqual(res["state"], "THERMAL_THROTTLED_PASSIVE")
        self.assertFalse(res["blockers"])
        self.assertTrue(any("passive throttling" in w for w in res["warnings"]))

    def test_critical_trip(self) -> None:
        res = evaluate_thermal_zones_state(self.critical)
        self.assertEqual(res["status"], "FAIL")
        self.assertEqual(res["state"], "THERMAL_CRITICAL_BLOCKED")
        self.assertTrue(any("critical trip" in b for b in res["blockers"]))
        self.assertTrue(any("Skin / chassis temperature exceeds critical" in b for b in res["blockers"]))

    def test_soc_critical_cutoff(self) -> None:
        data = json.loads(json.dumps(self.nominal))
        data["zones"]["soc_max"]["temp_mc"] = 117000
        res = evaluate_thermal_zones_state(data)
        self.assertEqual(res["status"], "FAIL")
        self.assertTrue(any("SoC maximum temperature reached critical trip" in b for b in res["blockers"]))

    def test_skin_critical_cutoff(self) -> None:
        data = json.loads(json.dumps(self.nominal))
        data["zones"]["skin_ntc"]["temp_mc"] = 45500
        res = evaluate_thermal_zones_state(data)
        self.assertEqual(res["status"], "FAIL")
        self.assertTrue(any("Skin / chassis temperature exceeds critical limit" in b for b in res["blockers"]))

    def test_boot_id_mismatch(self) -> None:
        data = json.loads(json.dumps(self.nominal))
        data["boot_id"] = "bad-boot-id"
        res = evaluate_thermal_zones_state(data)
        self.assertEqual(res["status"], "FAIL")
        self.assertTrue(any("Boot ID mismatch" in b for b in res["blockers"]))

    def test_missing_zones_warning(self) -> None:
        data = json.loads(json.dumps(self.nominal))
        del data["zones"]["skin_ntc"]
        res = evaluate_thermal_zones_state(data)
        self.assertEqual(res["status"], "WARN")
        self.assertTrue(any("Incomplete thermal zone inventory" in w for w in res["warnings"]))

    def test_cli_validate_offline(self) -> None:
        tool_script = TOOL_DIR / "lynx_thermal_zones_validator.py"
        fixture_path = FIXTURES_DIR / "thermal-nominal-quiescent.json"
        cmd = [sys.executable, str(tool_script), "--validate", str(fixture_path), "--json"]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
        out = json.loads(proc.stdout)
        self.assertEqual(out["status"], "OK")
        self.assertEqual(out["state"], "THERMAL_ENVELOPE_NOMINAL")

    def test_cli_live_safety_gate(self) -> None:
        tool_script = TOOL_DIR / "lynx_thermal_zones_validator.py"
        proc = subprocess.run(
            [sys.executable, str(tool_script), "--live"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("--allow-live", proc.stderr)

    def test_ast_safety_and_no_writes(self) -> None:
        source_path = TOOL_DIR / "lynx_thermal_zones_validator.py"
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
