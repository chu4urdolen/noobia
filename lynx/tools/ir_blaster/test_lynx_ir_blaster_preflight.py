#!/usr/bin/env python3
"""Unit tests for Lynx Consumer IR Blaster Preflight Tool."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess
import sys
import unittest

from lynx_ir_blaster_preflight import (
    evaluate_ir_blaster_state,
    PINNED_BOOT_ID,
    COMPATIBLE_PWM,
    COMPATIBLE_CORE,
)

TOOL_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = TOOL_DIR / "fixtures"


class TestLynxIrBlasterPreflight(unittest.TestCase):
    def setUp(self) -> None:
        with open(FIXTURES_DIR / "ir-blaster-bound.json", "r", encoding="utf-8") as f:
            self.bound = json.load(f)
        with open(FIXTURES_DIR / "ir-blaster-unbound.json", "r", encoding="utf-8") as f:
            self.unbound = json.load(f)
        with open(FIXTURES_DIR / "ir-blaster-missing-dt.json", "r", encoding="utf-8") as f:
            self.missing_dt = json.load(f)

    def test_bound_ready(self) -> None:
        res = evaluate_ir_blaster_state(self.bound)
        self.assertEqual(res["status"], "OK")
        self.assertEqual(res["state"], "BOUND_READY")
        self.assertFalse(res["blockers"])
        self.assertFalse(res["warnings"])
        self.assertTrue(res["details"]["device_tree"]["consumer_ir_pwm"]["present"])
        self.assertTrue(res["details"]["runtime"]["driver_bound"])
        self.assertTrue(res["details"]["runtime"]["dev_node_present"])

    def test_unbound_quiescent(self) -> None:
        res = evaluate_ir_blaster_state(self.unbound)
        self.assertEqual(res["status"], "OK")
        self.assertEqual(res["state"], "UNBOUND_QUIESCENT")
        self.assertFalse(res["blockers"])
        self.assertFalse(res["details"]["runtime"]["driver_bound"])

    def test_missing_dt(self) -> None:
        res = evaluate_ir_blaster_state(self.missing_dt)
        self.assertEqual(res["status"], "FAIL")
        self.assertEqual(res["state"], "MALFORMED_SPEC")
        self.assertTrue(any("consumerIr" in b for b in res["blockers"]))
        self.assertTrue(any("consumer_ir_core" in b for b in res["blockers"]))

    def test_boot_id_mismatch(self) -> None:
        data = json.loads(json.dumps(self.bound))
        data["boot_id"] = "wrong-boot-id"
        res = evaluate_ir_blaster_state(data)
        self.assertEqual(res["status"], "FAIL")
        self.assertTrue(any("Boot ID mismatch" in b for b in res["blockers"]))

    def test_carrier_frequency_warning(self) -> None:
        data = json.loads(json.dumps(self.bound))
        data["device_tree"]["consumer_ir_pwm"]["carrier_freq_hz"] = 20000
        res = evaluate_ir_blaster_state(data)
        self.assertEqual(res["status"], "WARN")
        self.assertTrue(any("carrier frequency" in w for w in res["warnings"]))

    def test_duty_cycle_warning(self) -> None:
        data = json.loads(json.dumps(self.bound))
        data["device_tree"]["consumer_ir_pwm"]["duty_cycle_pct"] = 80
        res = evaluate_ir_blaster_state(data)
        self.assertEqual(res["status"], "WARN")
        self.assertTrue(any("duty cycle" in w for w in res["warnings"]))

    def test_module_inactive_warning(self) -> None:
        data = json.loads(json.dumps(self.bound))
        data["modules"]["oplus_bsp_kookong_ir_pwm"] = False
        res = evaluate_ir_blaster_state(data)
        self.assertEqual(res["status"], "WARN")
        self.assertTrue(any("oplus_bsp_kookong_ir_pwm" in w for w in res["warnings"]))

    def test_cli_validate_offline(self) -> None:
        tool_script = TOOL_DIR / "lynx_ir_blaster_preflight.py"
        fixture_path = FIXTURES_DIR / "ir-blaster-bound.json"
        cmd = [sys.executable, str(tool_script), "--validate", str(fixture_path), "--json"]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
        out = json.loads(proc.stdout)
        self.assertEqual(out["status"], "OK")
        self.assertEqual(out["state"], "BOUND_READY")

    def test_cli_live_safety_gate(self) -> None:
        tool_script = TOOL_DIR / "lynx_ir_blaster_preflight.py"
        proc = subprocess.run(
            [sys.executable, str(tool_script), "--live"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("--allow-live", proc.stderr)

    def test_ast_safety_and_no_writes(self) -> None:
        source_path = TOOL_DIR / "lynx_ir_blaster_preflight.py"
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
