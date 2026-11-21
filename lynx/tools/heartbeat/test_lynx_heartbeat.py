#!/usr/bin/env python3
"""
Unit tests for Lynx Autonomous Health Heartbeat Publisher.
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
SRC_FILE = TOOLS_DIR / "lynx_heartbeat.py"

sys.path.insert(0, str(TOOLS_DIR))
import lynx_heartbeat as heartbeat  # type: ignore


class TestLynxHeartbeat(unittest.TestCase):
    def test_fixture_nominal(self):
        fpath = FIXTURES_DIR / "heartbeat-payload-nominal.json"
        with fpath.open("r", encoding="utf-8") as f:
            data = json.load(f)
        res = heartbeat.validate_heartbeat_payload(data)
        self.assertEqual(res.status, "OK")
        self.assertTrue(res.valid_schema)
        self.assertEqual(res.node_name, "lynx")
        self.assertEqual(res.battery_pct, 82)
        self.assertEqual(res.survival_policy, "NOMINAL_OPERATION")
        self.assertTrue(res.watchdog_active)

    def test_fixture_throttled(self):
        fpath = FIXTURES_DIR / "heartbeat-payload-throttled.json"
        with fpath.open("r", encoding="utf-8") as f:
            data = json.load(f)
        res = heartbeat.validate_heartbeat_payload(data)
        self.assertEqual(res.status, "WARN")
        self.assertEqual(res.survival_policy, "THERMAL_THROTTLE_PAUSE_CHG")
        self.assertTrue(any("high shell" in w.lower() for w in res.warnings))

    def test_fixture_corrupt(self):
        fpath = FIXTURES_DIR / "heartbeat-payload-corrupt.json"
        with fpath.open("r", encoding="utf-8") as f:
            data = json.load(f)
        res = heartbeat.validate_heartbeat_payload(data)
        self.assertEqual(res.status, "FAIL")
        self.assertFalse(res.valid_schema)
        self.assertTrue(len(res.errors) > 0)

    def test_synthesized_nominal_payload_valid(self):
        payload = heartbeat.synthesize_nominal_payload()
        res = heartbeat.validate_heartbeat_payload(payload)
        self.assertEqual(res.status, "OK")
        self.assertTrue(res.valid_schema)

    def test_cli_emit(self):
        cmd = [sys.executable, str(SRC_FILE), "--emit"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertEqual(data["node"], "lynx")

    def test_cli_validate_success(self):
        fpath = FIXTURES_DIR / "heartbeat-payload-nominal.json"
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

    def test_invalid_node_fails(self):
        payload = heartbeat.synthesize_nominal_payload()
        payload["node"] = "fake_host"
        res = heartbeat.validate_heartbeat_payload(payload)
        self.assertEqual(res.status, "FAIL")
        self.assertTrue(any("invalid node" in err.lower() for err in res.errors))

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


if __name__ == "__main__":
    unittest.main()
