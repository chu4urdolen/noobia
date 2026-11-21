#!/usr/bin/env python3
"""
Unit tests for Lynx Untethered Autonomy Readiness Preflight Checklist.
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
SRC_FILE = TOOLS_DIR / "lynx_autonomy_preflight.py"

sys.path.insert(0, str(TOOLS_DIR))
import lynx_autonomy_preflight as preflight  # type: ignore


class TestAutonomyPreflight(unittest.TestCase):
    def test_fixture_ready(self):
        fpath = FIXTURES_DIR / "autonomy-readiness-ready.json"
        with fpath.open("r", encoding="utf-8") as f:
            data = json.load(f)
        res = preflight.audit_autonomy_readiness(data)
        self.assertEqual(res.verdict, "READY_FOR_AUTONOMY")
        self.assertEqual(res.gates_passed, 6)
        self.assertEqual(len(res.blockers), 0)

    def test_fixture_degraded(self):
        fpath = FIXTURES_DIR / "autonomy-readiness-degraded.json"
        with fpath.open("r", encoding="utf-8") as f:
            data = json.load(f)
        res = preflight.audit_autonomy_readiness(data)
        self.assertEqual(res.verdict, "AUTONOMY_DEGRADED")
        self.assertEqual(len(res.blockers), 0)
        self.assertTrue(len(res.warnings) > 0)

    def test_fixture_blocked(self):
        fpath = FIXTURES_DIR / "autonomy-readiness-blocked.json"
        with fpath.open("r", encoding="utf-8") as f:
            data = json.load(f)
        res = preflight.audit_autonomy_readiness(data)
        self.assertEqual(res.verdict, "BLOCKED")
        self.assertTrue(len(res.blockers) > 0)

    def test_empty_gates_blocked(self):
        res = preflight.audit_autonomy_readiness({})
        self.assertEqual(res.verdict, "BLOCKED")

    def test_cell_delta_imbalance_blocker(self):
        data = {
            "gates": {
                "battery_pct": 90,
                "cell_delta_mv": 110,  # >= 100mV hazard
                "shell_temp_c": 30.0,
                "soc_max_temp_c": 40.0,
                "ufs_pre_eol": 1,
                "ufs_lifetime_est": 1,
                "watchdog_timeout_sec": 30,
                "watchdog_petting_sec": 5,
                "watchdog_bound": True,
                "survival_policy": "NOMINAL_OPERATION",
            }
        }
        res = preflight.audit_autonomy_readiness(data)
        self.assertEqual(res.verdict, "BLOCKED")
        self.assertTrue(any("imbalance" in b.lower() for b in res.blockers))

    def test_cli_validate_success(self):
        fpath = FIXTURES_DIR / "autonomy-readiness-ready.json"
        cmd = [sys.executable, str(SRC_FILE), "--validate", str(fpath)]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        out = json.loads(res.stdout)
        self.assertEqual(out["verdict"], "READY_FOR_AUTONOMY")

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
        self.assertIn(out["verdict"], ("READY_FOR_AUTONOMY", "AUTONOMY_DEGRADED"))

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

    def test_to_dict_contains_all_fields(self):
        fpath = FIXTURES_DIR / "autonomy-readiness-ready.json"
        with fpath.open("r", encoding="utf-8") as f:
            data = json.load(f)
        res = preflight.audit_autonomy_readiness(data)
        d = res.to_dict()
        self.assertIn("verdict", d)
        self.assertIn("gates_passed", d)
        self.assertIn("gate_results", d)
        self.assertIn("blockers", d)
        self.assertIn("warnings", d)


if __name__ == "__main__":
    unittest.main()
