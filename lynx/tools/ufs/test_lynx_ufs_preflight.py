#!/usr/bin/env python3
"""
Unit tests for UFS 3.1 Host Controller & Storage Subsystem Preflight Gate.
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
SRC_FILE = TOOLS_DIR / "lynx_ufs_preflight.py"

sys.path.insert(0, str(TOOLS_DIR))
import lynx_ufs_preflight as preflight  # type: ignore


class TestUfsPreflight(unittest.TestCase):
    def test_fixture_healthy(self):
        fpath = FIXTURES_DIR / "ufs-preflight-healthy.json"
        with fpath.open("r", encoding="utf-8") as f:
            data = json.load(f)
        status = preflight.evaluate_spec(data)
        self.assertEqual(status.status, "OK")
        self.assertTrue(status.valid_dt)
        self.assertTrue(status.clocks_ok)
        self.assertTrue(status.resets_ok)
        self.assertTrue(status.regulators_ok)
        self.assertTrue(status.driver_bound)
        self.assertEqual(status.pre_eol_status, "NORMAL")
        self.assertEqual(status.lifetime_est_a_pct, "0%-10%")

    def test_fixture_worn(self):
        fpath = FIXTURES_DIR / "ufs-preflight-worn.json"
        with fpath.open("r", encoding="utf-8") as f:
            data = json.load(f)
        status = preflight.evaluate_spec(data)
        self.assertEqual(status.status, "FAIL")
        self.assertIn("WARNING", status.pre_eol_status)
        self.assertTrue(any("lifetime exhausted" in err.lower() for err in status.errors))

    def test_fixture_missing_dt(self):
        fpath = FIXTURES_DIR / "ufs-preflight-missing-dt.json"
        with fpath.open("r", encoding="utf-8") as f:
            data = json.load(f)
        status = preflight.evaluate_spec(data)
        self.assertEqual(status.status, "FAIL")
        self.assertFalse(status.valid_dt)
        self.assertFalse(status.clocks_ok)

    def test_missing_clocks_fails_validation(self):
        data = {
            "device_tree": {
                "node": "ufshci@112b0000",
                "compatible": "mediatek,mt8183-ufshci",
                "base_address": "0x112b0000",
                "interrupt": 169,
                "clocks": ["ufs"],  # missing 4 other clocks
                "resets": ["unipro_rst", "crypto_rst", "hci_rst"],
            },
            "runtime": {"driver_bound": True},
        }
        status = preflight.evaluate_spec(data)
        self.assertEqual(status.status, "FAIL")
        self.assertFalse(status.clocks_ok)
        self.assertTrue(any("clocks" in err.lower() for err in status.errors))

    def test_pre_eol_urgent_failure(self):
        data = {
            "device_tree": {
                "node": "ufshci@112b0000",
                "compatible": "mediatek,mt8183-ufshci",
                "base_address": "0x112b0000",
                "interrupt": 169,
                "clocks": ["ufs_hd_haxi", "ufs_fde", "ufs", "ufs_mbist", "ufs_hf_fmem"],
                "resets": ["unipro_rst", "crypto_rst", "hci_rst"],
            },
            "runtime": {
                "driver_bound": True,
                "health_descriptor": {
                    "pre_eol_info": 3,  # Urgent
                    "lifetime_estimation_a": 2,
                    "lifetime_estimation_b": 2,
                },
            },
        }
        status = preflight.evaluate_spec(data)
        self.assertEqual(status.status, "FAIL")
        self.assertIn("URGENT", status.pre_eol_status)
        self.assertTrue(any("urgent" in err.lower() for err in status.errors))

    def test_cli_validate_success(self):
        fpath = FIXTURES_DIR / "ufs-preflight-healthy.json"
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
        # On host without phone connected, returns WARN (exit code 0)
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

    def test_lifetime_decoder_ranges(self):
        desc, sev = preflight._decode_lifetime(1)
        self.assertEqual(desc, "0%-10%")
        self.assertEqual(sev, "OK")

        desc, sev = preflight._decode_lifetime(9)
        self.assertEqual(desc, "80%-90% (HIGH_WEAR)")
        self.assertEqual(sev, "WARN")

        desc, sev = preflight._decode_lifetime(10)
        self.assertEqual(sev, "FAIL")

        desc, sev = preflight._decode_lifetime(11)
        self.assertEqual(desc, "EXCEEDED_LIFETIME")
        self.assertEqual(sev, "FAIL")


if __name__ == "__main__":
    unittest.main()
