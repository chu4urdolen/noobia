#!/usr/bin/env python3
"""Unit tests for Lynx USB-C DisplayPort Alt Mode & Redriver Preflight Tool."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess
import sys
import unittest

from lynx_usb_dp_preflight import (
    evaluate_usb_dp_state,
    PINNED_BOOT_ID,
    DP_SVID_HEX,
)

TOOL_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = TOOL_DIR / "fixtures"


class TestLynxUsbDpPreflight(unittest.TestCase):
    def setUp(self) -> None:
        with open(FIXTURES_DIR / "usb-dp-baseline-disconnected.json", "r", encoding="utf-8") as f:
            self.baseline = json.load(f)
        with open(FIXTURES_DIR / "usb-dp-altmode-connected.json", "r", encoding="utf-8") as f:
            self.altmode_connected = json.load(f)
        with open(FIXTURES_DIR / "usb-dp-mux-failure.json", "r", encoding="utf-8") as f:
            self.mux_failure = json.load(f)

    def test_baseline_disconnected(self) -> None:
        res = evaluate_usb_dp_state(self.baseline)
        self.assertEqual(res["status"], "OK")
        self.assertEqual(res["state"], "DP_STANDBY_DISCONNECTED")
        self.assertFalse(res["blockers"])
        self.assertFalse(res["warnings"])
        self.assertTrue(res["details"]["redriver"]["present"])
        self.assertTrue(res["details"]["selector"]["present"])
        self.assertFalse(res["details"]["tcpc"]["altmode_active"])

    def test_altmode_connected_pin_c(self) -> None:
        res = evaluate_usb_dp_state(self.altmode_connected)
        self.assertEqual(res["status"], "OK")
        self.assertEqual(res["state"], "DP_ALTMODE_ACTIVE")
        self.assertFalse(res["blockers"])
        self.assertTrue(res["details"]["tcpc"]["altmode_active"])
        self.assertEqual(res["details"]["tcpc"]["pin_assignment"], "C")
        self.assertEqual(res["details"]["tcpc"]["hpd"], "1")

    def test_altmode_pin_d_multifunction(self) -> None:
        data = json.loads(json.dumps(self.altmode_connected))
        data["tcpc"]["pin_assignment"] = "D"
        res = evaluate_usb_dp_state(data)
        self.assertEqual(res["status"], "OK")
        self.assertEqual(res["state"], "DP_ALTMODE_ACTIVE")
        self.assertEqual(res["details"]["tcpc"]["pin_assignment"], "D")

    def test_mux_hardware_failure(self) -> None:
        res = evaluate_usb_dp_state(self.mux_failure)
        self.assertEqual(res["status"], "FAIL")
        self.assertEqual(res["state"], "HARDWARE_FAULT")
        self.assertTrue(any("redriver node missing" in b for b in res["blockers"]))
        self.assertTrue(any("class interface missing" in b for b in res["blockers"]))

    def test_boot_id_mismatch(self) -> None:
        data = json.loads(json.dumps(self.baseline))
        data["boot_id"] = "bad-boot-id-0000"
        res = evaluate_usb_dp_state(data)
        self.assertEqual(res["status"], "FAIL")
        self.assertTrue(any("Boot ID mismatch" in b for b in res["blockers"]))

    def test_invalid_pin_assignment(self) -> None:
        data = json.loads(json.dumps(self.altmode_connected))
        data["tcpc"]["pin_assignment"] = "Z"
        res = evaluate_usb_dp_state(data)
        self.assertEqual(res["status"], "FAIL")
        self.assertTrue(any("unsupported DP pin assignment" in b for b in res["blockers"]))

    def test_invalid_svid_when_altmode_active(self) -> None:
        data = json.loads(json.dumps(self.altmode_connected))
        data["tcpc"]["svid"] = "0x1234"
        res = evaluate_usb_dp_state(data)
        self.assertEqual(res["status"], "FAIL")
        self.assertTrue(any("Active Alt Mode SVID mismatch" in b for b in res["blockers"]))

    def test_cli_validate_offline(self) -> None:
        tool_script = TOOL_DIR / "lynx_usb_dp_preflight.py"
        fixture_path = FIXTURES_DIR / "usb-dp-baseline-disconnected.json"
        cmd = [sys.executable, str(tool_script), "--validate", str(fixture_path), "--json"]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
        out = json.loads(proc.stdout)
        self.assertEqual(out["status"], "OK")
        self.assertEqual(out["state"], "DP_STANDBY_DISCONNECTED")

    def test_cli_live_safety_gate(self) -> None:
        tool_script = TOOL_DIR / "lynx_usb_dp_preflight.py"
        # --live without --allow-live must exit non-zero
        proc = subprocess.run(
            [sys.executable, str(tool_script), "--live"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("--allow-live", proc.stderr)

    def test_ast_safety_and_no_writes(self) -> None:
        source_path = TOOL_DIR / "lynx_usb_dp_preflight.py"
        with open(source_path, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)

        # Assert no forbidden network or socket imports
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
