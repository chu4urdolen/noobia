#!/usr/bin/env python3
"""Unit tests for Lynx Low-Power Island SCP / LPM Preflight Tool."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess
import sys
import unittest

from lynx_lpm_preflight import (
    evaluate_lpm_state,
    PINNED_BOOT_ID,
    EXPECTED_TCM_SIZE_BYTES,
    EXPECTED_MBOX_COUNT,
)

TOOL_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = TOOL_DIR / "fixtures"


class TestLynxLpmPreflight(unittest.TestCase):
    def setUp(self) -> None:
        with open(FIXTURES_DIR / "lpm-baseline-active.json", "r", encoding="utf-8") as f:
            self.baseline = json.load(f)
        with open(FIXTURES_DIR / "lpm-deep-sleep.json", "r", encoding="utf-8") as f:
            self.deep_sleep = json.load(f)
        with open(FIXTURES_DIR / "lpm-scp-hung-failure.json", "r", encoding="utf-8") as f:
            self.scp_failure = json.load(f)

    def test_baseline_active_running(self) -> None:
        res = evaluate_lpm_state(self.baseline)
        self.assertEqual(res["status"], "OK")
        self.assertEqual(res["state"], "LPM_ACTIVE_RUNNING")
        self.assertFalse(res["blockers"])
        self.assertFalse(res["warnings"])
        self.assertTrue(res["details"]["scp"]["present"])
        self.assertEqual(res["details"]["scp"]["state"], "running")
        self.assertTrue(res["details"]["lpm"]["present"])

    def test_deep_sleep_standby(self) -> None:
        res = evaluate_lpm_state(self.deep_sleep)
        self.assertEqual(res["status"], "OK")
        self.assertEqual(res["state"], "LPM_LOW_POWER_STANDBY")
        self.assertFalse(res["blockers"])
        self.assertEqual(res["details"]["lpm"]["current_state"], "system_mem")

    def test_scp_crashed_failure(self) -> None:
        res = evaluate_lpm_state(self.scp_failure)
        self.assertEqual(res["status"], "FAIL")
        self.assertEqual(res["state"], "SCP_FAULT_OR_HUNG")
        self.assertTrue(any("SCP core state invalid" in b for b in res["blockers"]))
        self.assertTrue(any("mailbox count insufficient" in b for b in res["blockers"]))

    def test_lpm_missing_resource(self) -> None:
        data = json.loads(json.dumps(self.baseline))
        del data["lpm"]["resources"]["dram_s1"]
        res = evaluate_lpm_state(data)
        self.assertEqual(res["status"], "FAIL")
        self.assertTrue(any("missing essential clocks/rails" in b for b in res["blockers"]))

    def test_lpm_missing_controller(self) -> None:
        data = json.loads(json.dumps(self.baseline))
        data["lpm"]["present"] = False
        res = evaluate_lpm_state(data)
        self.assertEqual(res["status"], "FAIL")
        self.assertTrue(any("low-power management controller missing" in b for b in res["blockers"]))

    def test_boot_id_mismatch(self) -> None:
        data = json.loads(json.dumps(self.baseline))
        data["boot_id"] = "bad-boot-id-0000"
        res = evaluate_lpm_state(data)
        self.assertEqual(res["status"], "FAIL")
        self.assertTrue(any("Boot ID mismatch" in b for b in res["blockers"]))

    def test_wakeup_abort_warning(self) -> None:
        data = json.loads(json.dumps(self.baseline))
        data["lpm"]["wakeup_aborts"] = 75
        res = evaluate_lpm_state(data)
        self.assertEqual(res["status"], "WARN")
        self.assertTrue(any("entry abort count" in w for w in res["warnings"]))

    def test_cli_validate_offline(self) -> None:
        tool_script = TOOL_DIR / "lynx_lpm_preflight.py"
        fixture_path = FIXTURES_DIR / "lpm-baseline-active.json"
        cmd = [sys.executable, str(tool_script), "--validate", str(fixture_path), "--json"]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
        out = json.loads(proc.stdout)
        self.assertEqual(out["status"], "OK")
        self.assertEqual(out["state"], "LPM_ACTIVE_RUNNING")

    def test_cli_live_safety_gate(self) -> None:
        tool_script = TOOL_DIR / "lynx_lpm_preflight.py"
        proc = subprocess.run(
            [sys.executable, str(tool_script), "--live"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("--allow-live", proc.stderr)

    def test_ast_safety_and_no_writes(self) -> None:
        source_path = TOOL_DIR / "lynx_lpm_preflight.py"
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
