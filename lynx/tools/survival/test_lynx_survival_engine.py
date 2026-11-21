#!/usr/bin/env python3
"""
Unit tests for Lynx Autonomous Survival Decision Engine.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = TOOLS_DIR / "fixtures"
SRC_FILE = TOOLS_DIR / "lynx_survival_engine.py"

sys.path.insert(0, str(TOOLS_DIR))
import lynx_survival_engine as engine  # type: ignore


class TestSurvivalEngine(unittest.TestCase):
    def test_fixture_nominal(self):
        fpath = FIXTURES_DIR / "survival-state-nominal.json"
        with fpath.open("r", encoding="utf-8") as f:
            data = json.load(f)
        verdict = engine.evaluate_telemetry(data)
        self.assertEqual(verdict.status, "OK")
        self.assertEqual(verdict.policy_state, "NOMINAL_OPERATION")
        self.assertEqual(verdict.recommended_agent_duty_cycle, "FULL_AUTONOMY")

    def test_fixture_throttle(self):
        fpath = FIXTURES_DIR / "survival-state-throttle.json"
        with fpath.open("r", encoding="utf-8") as f:
            data = json.load(f)
        verdict = engine.evaluate_telemetry(data)
        self.assertEqual(verdict.status, "WARN")
        self.assertEqual(verdict.policy_state, "THERMAL_THROTTLE_PAUSE_CHG")
        self.assertEqual(verdict.recommended_cpu_governor, "powersave")

    def test_fixture_suspend(self):
        fpath = FIXTURES_DIR / "survival-state-suspend.json"
        with fpath.open("r", encoding="utf-8") as f:
            data = json.load(f)
        verdict = engine.evaluate_telemetry(data)
        self.assertEqual(verdict.status, "WARN")
        self.assertEqual(verdict.policy_state, "LOW_POWER_SUSPEND")
        self.assertEqual(verdict.recommended_agent_duty_cycle, "SUSPEND_SLEEP")

    def test_fixture_emergency(self):
        fpath = FIXTURES_DIR / "survival-state-emergency.json"
        with fpath.open("r", encoding="utf-8") as f:
            data = json.load(f)
        verdict = engine.evaluate_telemetry(data)
        self.assertEqual(verdict.status, "CRITICAL")
        self.assertEqual(verdict.policy_state, "EMERGENCY_SHUTDOWN")
        self.assertEqual(verdict.recommended_agent_duty_cycle, "TERMINATE")

    def test_empty_telemetry_returns_critical(self):
        verdict = engine.evaluate_telemetry({})
        self.assertEqual(verdict.status, "CRITICAL")
        self.assertEqual(verdict.policy_state, "UNKNOWN")

    def test_cli_validate_success(self):
        fpath = FIXTURES_DIR / "survival-state-nominal.json"
        cmd = [sys.executable, str(SRC_FILE), "--validate", str(fpath)]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        out = json.loads(res.stdout)
        self.assertEqual(out["status"], "OK")

    def test_cli_live_safety_gate(self):
        cmd = [sys.executable, str(SRC_FILE), "--live"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res.returncode, 2)
        self.assertIn("requires explicit --allow-live", res.stderr)

    def test_cli_live_with_allow_live(self):
        cmd = [sys.executable, str(SRC_FILE), "--live", "--allow-live"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        out = json.loads(res.stdout)
        self.assertEqual(out["status"], "OK")

    def test_ast_safety_and_no_writes(self):
        with SRC_FILE.open("r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(SRC_FILE))

        forbidden_names = {"remove", "rmdir", "unlink"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in forbidden_names:
                self.fail(f"Forbidden mutating attribute call found in AST: {node.attr}")
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "open":
                    for arg in node.args[1:]:
                        if isinstance(arg, ast.Constant) and any(m in str(arg.value) for m in ("w", "a", "+")):
                            self.fail("Writable open() mode detected in AST")

    def test_decision_priority_emergency_over_throttle(self):
        # Battery critical (3%) AND Thermal high (43C) -> EMERGENCY_SHUTDOWN must take precedence
        data = {
            "telemetry": {
                "battery_pct": 3,
                "shell_temp_c": 43.0,
                "soc_max_temp_c": 85.0,
            }
        }
        verdict = engine.evaluate_telemetry(data)
        self.assertEqual(verdict.policy_state, "EMERGENCY_SHUTDOWN")
        self.assertEqual(verdict.status, "CRITICAL")


if __name__ == "__main__":
    unittest.main()
