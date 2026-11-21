#!/usr/bin/env python3
"""
Unit tests for Hardware Watchdog (MTK-WDT) Preflight Gate.
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
SRC_FILE = TOOLS_DIR / "lynx_watchdog_preflight.py"

sys.path.insert(0, str(TOOLS_DIR))
import lynx_watchdog_preflight as preflight  # type: ignore


class TestWatchdogPreflight(unittest.TestCase):
    def test_fixture_ready(self):
        fpath = FIXTURES_DIR / "watchdog-preflight-ready.json"
        with fpath.open("r", encoding="utf-8") as f:
            data = json.load(f)
        status = preflight.evaluate_spec(data)
        self.assertEqual(status.status, "OK")
        self.assertTrue(status.valid_dt)
        self.assertTrue(status.reboot_mode_ok)
        self.assertTrue(status.driver_bound)
        self.assertEqual(status.configured_timeout_sec, 30)
        self.assertEqual(status.petting_cadence_sec, 5)
        self.assertEqual(status.safety_margin_ratio, 6.0)

    def test_fixture_unbound(self):
        fpath = FIXTURES_DIR / "watchdog-preflight-unbound.json"
        with fpath.open("r", encoding="utf-8") as f:
            data = json.load(f)
        status = preflight.evaluate_spec(data)
        self.assertEqual(status.status, "WARN")
        self.assertTrue(status.valid_dt)
        self.assertFalse(status.driver_bound)
        self.assertTrue(any("unbound" in w.lower() or "not bound" in w.lower() for w in status.warnings))

    def test_fixture_missing_dt(self):
        fpath = FIXTURES_DIR / "watchdog-preflight-missing-dt.json"
        with fpath.open("r", encoding="utf-8") as f:
            data = json.load(f)
        status = preflight.evaluate_spec(data)
        self.assertEqual(status.status, "FAIL")
        self.assertFalse(status.valid_dt)

    def test_timeout_out_of_bounds_fails(self):
        data = {
            "device_tree": {
                "node": "watchdog@1c007000",
                "compatible": "mediatek,mt6983-wdt",
                "base_address": "0x1c007000",
            },
            "runtime": {
                "driver_bound": True,
                "configured_timeout_sec": 60,  # exceeds MT6983 max 32s hardware register
                "petting_cadence_sec": 5,
            },
        }
        status = preflight.evaluate_spec(data)
        self.assertEqual(status.status, "FAIL")
        self.assertTrue(any("bounds" in err.lower() for err in status.errors))

    def test_narrow_margin_warns(self):
        data = {
            "device_tree": {
                "node": "watchdog@1c007000",
                "compatible": "mediatek,mt6983-wdt",
                "base_address": "0x1c007000",
            },
            "runtime": {
                "driver_bound": True,
                "configured_timeout_sec": 4,
                "petting_cadence_sec": 3,  # ratio 1.33x < 2.0x
            },
        }
        status = preflight.evaluate_spec(data)
        self.assertEqual(status.status, "WARN")
        self.assertTrue(any("narrow" in w.lower() for w in status.warnings))

    def test_cli_validate_success(self):
        fpath = FIXTURES_DIR / "watchdog-preflight-ready.json"
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

    def test_never_touches_dev_watchdog_in_code(self):
        # The character device /dev/watchdog must NEVER be contacted or opened in code; only sysfs is allowed
        with SRC_FILE.open("r", encoding="utf-8") as f:
            content = f.read()
        self.assertNotIn('"/dev/watchdog"', content)
        self.assertNotIn("'/dev/watchdog'", content)


if __name__ == "__main__":
    unittest.main()
