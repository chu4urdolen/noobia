#!/usr/bin/env python3
"""
Unit tests for OnePlus Alert Slider (Tri-State Key) Hardware Preflight Gate.
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
SRC_FILE = TOOLS_DIR / "lynx_tri_state_key_preflight.py"

sys.path.insert(0, str(TOOLS_DIR))
import lynx_tri_state_key_preflight as preflight  # type: ignore


class TestTriStateKeyPreflight(unittest.TestCase):
    def test_fixture_silent(self):
        fpath = FIXTURES_DIR / "tri-state-key-preflight-silent.json"
        with fpath.open("r", encoding="utf-8") as f:
            data = json.load(f)
        status = preflight.evaluate_spec(data)
        self.assertEqual(status.status, "OK")
        self.assertTrue(status.valid_dt)
        self.assertTrue(status.i2c_bus_ok)
        self.assertTrue(status.uphall_ok)
        self.assertTrue(status.downhall_ok)
        self.assertEqual(status.slider_position, "SILENT")

    def test_fixture_vibrate(self):
        fpath = FIXTURES_DIR / "tri-state-key-preflight-vibrate.json"
        with fpath.open("r", encoding="utf-8") as f:
            data = json.load(f)
        status = preflight.evaluate_spec(data)
        self.assertEqual(status.status, "OK")
        self.assertEqual(status.slider_position, "VIBRATE")

    def test_fixture_ring(self):
        fpath = FIXTURES_DIR / "tri-state-key-preflight-ring.json"
        with fpath.open("r", encoding="utf-8") as f:
            data = json.load(f)
        status = preflight.evaluate_spec(data)
        self.assertEqual(status.status, "OK")
        self.assertEqual(status.slider_position, "RING")

    def test_fixture_missing_dt(self):
        fpath = FIXTURES_DIR / "tri-state-key-preflight-missing-dt.json"
        with fpath.open("r", encoding="utf-8") as f:
            data = json.load(f)
        status = preflight.evaluate_spec(data)
        self.assertEqual(status.status, "FAIL")
        self.assertFalse(status.valid_dt)
        self.assertTrue(len(status.errors) > 0)

    def test_ambiguous_magnetic_state(self):
        data = {
            "device_tree": {
                "i2c_bus": "i2c@11e00000",
                "i2c_compatible": "mediatek,mt6983-i2c",
                "downhall": {
                    "compatible": "oplus,hall-mxm1120,down",
                    "dhall_id": 2,
                    "irq_gpio": 5,
                },
                "uphall": {
                    "compatible": "oplus,hall-mxm1120,up",
                    "dhall_id": 1,
                    "irq_gpio": 4,
                },
                "supplies": {"vio": "VIO18", "vdd": "VIO28"},
            },
            "runtime": {
                "driver_bound": True,
                "uphall_triggered": True,
                "downhall_triggered": True,
            },
        }
        status = preflight.evaluate_spec(data)
        self.assertEqual(status.status, "FAIL")
        self.assertEqual(status.slider_position, "AMBIGUOUS")
        self.assertTrue(any("anomaly" in err.lower() for err in status.errors))

    def test_second_source_ist8801(self):
        data = {
            "device_tree": {
                "i2c_bus": "i2c@11e00000",
                "i2c_compatible": "mediatek,mt6983-i2c",
                "downhall": {
                    "compatible": "oplus,hall-ist8801,down",
                    "dhall_id": 2,
                    "irq_gpio": 5,
                },
                "uphall": {
                    "compatible": "oplus,hall-ist8801,up",
                    "dhall_id": 1,
                    "irq_gpio": 4,
                },
                "supplies": {"vio": "VIO18", "vdd": "VIO28"},
            },
            "runtime": {
                "driver_bound": True,
                "uphall_triggered": True,
                "downhall_triggered": False,
            },
        }
        status = preflight.evaluate_spec(data)
        self.assertEqual(status.status, "OK")
        self.assertTrue(status.valid_dt)
        self.assertEqual(status.slider_position, "SILENT")

    def test_cli_validate_success(self):
        fpath = FIXTURES_DIR / "tri-state-key-preflight-silent.json"
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
        # On host machine without phone connected, unbound state returns WARN (exit code 0)
        self.assertEqual(res.returncode, 0)
        out = json.loads(res.stdout)
        self.assertIn(out["status"], ("OK", "WARN"))

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
