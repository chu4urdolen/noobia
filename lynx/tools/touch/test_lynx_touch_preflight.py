#!/usr/bin/env python3
"""Unit tests for Lynx Synaptics S3908 touchscreen controller preflight."""

import ast
import json
from pathlib import Path
import subprocess
import sys
import unittest

from lynx_touch_preflight import (
    EXPECTED_CHIP_NAME,
    EXPECTED_COMPATIBLE,
    EXPECTED_DISPLAY_H,
    EXPECTED_DISPLAY_W,
    EXPECTED_I2C_ADDR,
    EXPECTED_I2C_BUS,
    EXPECTED_I2C_HZ,
    EXPECTED_IRQ_GPIO,
    EXPECTED_MAX_POINTS,
    EXPECTED_RESET_GPIO,
    EXPECTED_REPORT_RATE,
    EXPECTED_RX,
    EXPECTED_TX,
    EXPECTED_VCC_SUPPLY,
    EXPECTED_VCC_UV,
    EXPECTED_VDD_SUPPLY,
    EXPECTED_VDD_UV,
    LIVE_COLLECT_SCRIPT,
    evaluate_touch_preflight,
    validate_touch_spec,
)

HERE = Path(__file__).resolve().parent
FIXTURES_DIR = HERE / "fixtures"
TOOL = HERE / "lynx_touch_preflight.py"


def spec_doc() -> dict:
    """Return a valid board-spec document (from the bound fixture)."""
    return json.loads((FIXTURES_DIR / "touch-preflight-bound.json").read_text())


class TestExpectedConstants(unittest.TestCase):
    def test_compatible_is_synaptics_s3908(self):
        self.assertEqual(EXPECTED_COMPATIBLE, "synaptics-s3908")
        self.assertEqual(EXPECTED_CHIP_NAME, "S3908")

    def test_i2c_placement_matches_board_dts(self):
        self.assertEqual(EXPECTED_I2C_BUS, 0)
        self.assertEqual(EXPECTED_I2C_HZ, 400000)
        self.assertEqual(EXPECTED_I2C_ADDR, "0x4b")

    def test_gpio_map_matches_board_dts(self):
        self.assertEqual(EXPECTED_IRQ_GPIO, 8)
        self.assertEqual(EXPECTED_RESET_GPIO, 3)

    def test_power_rails_match_board_dts(self):
        self.assertEqual(EXPECTED_VDD_SUPPLY, "mt6373_vtp")
        self.assertEqual(EXPECTED_VDD_UV, 3000000)
        self.assertEqual(EXPECTED_VCC_SUPPLY, "mt6373_vmc")
        self.assertEqual(EXPECTED_VCC_UV, 1800000)

    def test_geometry_matches_board_dts(self):
        self.assertEqual(EXPECTED_TX, 17)
        self.assertEqual(EXPECTED_RX, 38)
        self.assertEqual(EXPECTED_MAX_POINTS, 10)
        self.assertEqual(EXPECTED_DISPLAY_W, 1440)
        self.assertEqual(EXPECTED_DISPLAY_H, 3216)

    def test_report_rate_matches_s3908_node(self):
        self.assertEqual(EXPECTED_REPORT_RATE, 60)


class TestSpecValidation(unittest.TestCase):
    def test_valid_spec_passes(self):
        ok, failures = validate_touch_spec(spec_doc())
        self.assertTrue(ok)
        self.assertEqual(failures, [])

    def test_corrupted_irq_gpio_rejected(self):
        doc = spec_doc()
        doc["gpios"]["irq"] = 9
        ok, failures = validate_touch_spec(doc)
        self.assertFalse(ok)
        self.assertIn("gpio_irq_mismatch_9_vs_8", failures)

    def test_corrupted_reset_gpio_rejected(self):
        doc = spec_doc()
        doc["gpios"]["reset"] = 4
        ok, failures = validate_touch_spec(doc)
        self.assertFalse(ok)
        self.assertIn("gpio_reset_mismatch_4_vs_3", failures)

    def test_corrupted_vdd_rail_rejected(self):
        doc = spec_doc()
        doc["rails"]["vdd_supply"] = "mt6373_vmch"
        ok, failures = validate_touch_spec(doc)
        self.assertFalse(ok)
        self.assertIn("rail_vdd_supply_mismatch_mt6373_vmch_vs_mt6373_vtp", failures)

    def test_corrupted_geometry_rejected(self):
        doc = spec_doc()
        doc["geometry"]["tx"] = 16
        doc["geometry"]["display_h"] = 3120
        ok, failures = validate_touch_spec(doc)
        self.assertFalse(ok)
        self.assertIn("geometry_tx_mismatch_16_vs_17", failures)
        self.assertIn("geometry_display_h_mismatch_3120_vs_3216", failures)

    def test_corrupted_report_rate_rejected(self):
        doc = spec_doc()
        doc["reporting"]["report_rate_default"] = 120
        ok, failures = validate_touch_spec(doc)
        self.assertFalse(ok)
        self.assertIn("report_rate_mismatch_120_vs_60", failures)

    def test_missing_touch_node_rejected(self):
        doc = spec_doc()
        doc["device_tree"]["touch_node_present"] = False
        ok, failures = validate_touch_spec(doc)
        self.assertFalse(ok)
        self.assertIn("missing_touch_node_in_dt", failures)

    def test_wrong_i2c_placement_rejected(self):
        doc = spec_doc()
        doc["device_tree"]["i2c_bus"] = 1
        doc["device_tree"]["i2c_addr"] = "0x5d"
        ok, failures = validate_touch_spec(doc)
        self.assertFalse(ok)
        self.assertIn("i2c_bus_mismatch_1_vs_0", failures)
        self.assertIn("i2c_addr_mismatch_0x5d_vs_0x4b", failures)


class TestEvaluator(unittest.TestCase):
    def test_bound_fixture_classifies_bound_ready(self):
        verdict = evaluate_touch_preflight(spec_doc())
        self.assertTrue(verdict.is_valid)
        self.assertEqual(verdict.status, "BOUND_READY")
        self.assertTrue(verdict.touch_driver_bound)
        self.assertTrue(verdict.input_device_present)

    def test_unbound_fixture_classifies_quiescent(self):
        data = spec_doc()
        data["runtime"] = {
            "i2c_client_present": False,
            "touch_driver_bound": False,
            "input_device_present": False,
            "input_device_name": None,
        }
        verdict = evaluate_touch_preflight(data)
        self.assertTrue(verdict.is_valid)
        self.assertEqual(verdict.status, "UNBOUND_QUIESCENT")

    def test_partial_enumeration_classification(self):
        data = spec_doc()
        data["runtime"]["touch_driver_bound"] = True
        data["runtime"]["input_device_present"] = False
        data["loaded_modules"] = []
        verdict = evaluate_touch_preflight(data)
        self.assertTrue(verdict.is_valid)
        self.assertEqual(verdict.status, "PARTIAL_ENUMERATED")

    def test_missing_runtime_section_defaults_to_quiescent(self):
        data = spec_doc()
        del data["runtime"]
        del data["loaded_modules"]
        verdict = evaluate_touch_preflight(data)
        self.assertTrue(verdict.is_valid)
        self.assertEqual(verdict.status, "UNBOUND_QUIESCENT")

    def test_malformed_spec_fixture_rejected(self):
        data = json.loads(
            (FIXTURES_DIR / "touch-preflight-missing-dt.json").read_text()
        )
        verdict = evaluate_touch_preflight(data)
        self.assertFalse(verdict.is_valid)
        self.assertEqual(verdict.status, "MALFORMED_SPEC")
        self.assertIn(
            "compatible_mismatch_goodix,gt9886_vs_synaptics-s3908",
            verdict.failures,
        )

    def test_to_dict_contains_all_fields(self):
        verdict = evaluate_touch_preflight(spec_doc())
        d = verdict.to_dict()
        for key in (
            "status", "is_valid", "touch_node_mapped", "i2c_address_mapped",
            "gpio_map_mapped", "power_rails_mapped", "geometry_mapped",
            "reporting_mapped", "touch_driver_bound", "input_device_present",
            "summary", "failures", "details",
        ):
            self.assertIn(key, d)


class TestCli(unittest.TestCase):
    def run_tool(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(TOOL), *args],
            capture_output=True, text=True, timeout=30,
        )

    def test_cli_fixture_bound_exit_zero(self):
        res = self.run_tool(str(FIXTURES_DIR / "touch-preflight-bound.json"))
        self.assertEqual(res.returncode, 0, res.stderr)
        payload = json.loads(res.stdout)
        self.assertEqual(payload["status"], "BOUND_READY")

    def test_cli_fixture_unbound_exit_zero(self):
        res = self.run_tool(str(FIXTURES_DIR / "touch-preflight-unbound.json"))
        self.assertEqual(res.returncode, 0, res.stderr)
        payload = json.loads(res.stdout)
        self.assertEqual(payload["status"], "UNBOUND_QUIESCENT")

    def test_cli_fixture_missing_dt_exit_one(self):
        res = self.run_tool(str(FIXTURES_DIR / "touch-preflight-missing-dt.json"))
        self.assertEqual(res.returncode, 1)
        payload = json.loads(res.stdout)
        self.assertEqual(payload["status"], "MALFORMED_SPEC")

    def test_cli_live_gate_requires_allow_live(self):
        res = self.run_tool("--live", "--host", "127.0.0.1")
        self.assertEqual(res.returncode, 2)
        self.assertIn("--allow-live", res.stderr)

    def test_cli_no_args_prints_help(self):
        res = self.run_tool()
        self.assertEqual(res.returncode, 0)
        self.assertIn("usage:", res.stdout.lower())


class TestSafetyBoundaries(unittest.TestCase):
    def test_live_script_is_readonly(self):
        forbidden = (
            "insmod", "rmmod", "modprobe", "setprop", "reboot", "shutdown",
            "kill", "tee", " > /sys", " > /proc", " > /etc", "dd of=",
            "mkfs", "rm -", "mv ", "cp ",
        )
        for token in forbidden:
            self.assertNotIn(token, LIVE_COLLECT_SCRIPT,
                             f"forbidden token in live script: {token}")

    def test_live_script_uses_only_whitelisted_commands(self):
        allowed = {"cat", "ls", "find", "readlink", "tr", "echo",
                   "for", "do", "done", "true", "sh"}
        import re
        commands = set(
            re.findall(r"^\s*([a-z_][a-z0-9_]*)\s", LIVE_COLLECT_SCRIPT,
                       flags=re.MULTILINE)
        )
        for cmd in commands:
            self.assertIn(cmd, allowed,
                          f"non-whitelisted command in live script: {cmd}")

    def test_tool_imports_are_harmless(self):
        tree = ast.parse(TOOL.read_text())
        allowed_modules = {
            "dataclasses", "json", "pathlib", "subprocess", "sys", "typing",
            "argparse",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertIn(alias.name.split(".")[0], allowed_modules)
            elif isinstance(node, ast.ImportFrom):
                self.assertIn((node.module or "").split(".")[0], allowed_modules)

    def test_no_unapproved_local_calls(self):
        local_calls = HERE.parent / "local_calls"
        if not local_calls.is_dir():
            self.skipTest("local_calls directory absent")
        touch_rows = sorted(p.name for p in local_calls.rglob("*touch*"))
        # Only the previously approved status pair (commit 88a913f) and the
        # approved non-consuming touch events pair (commit 0a662a1) may exist.
        expected = ["lynx_touch_status.json", "lynx_touch_status.sh"]
        if "lynx_touch_events.json" in touch_rows:
            expected = sorted(expected + ["lynx_touch_events.json", "lynx_touch_events.sh"])
        self.assertEqual(touch_rows, expected)
        # The preflight tool must not be wired into the agent catalog.
        for name in touch_rows:
            content = (local_calls / name).read_text()
            self.assertNotIn("lynx_touch_preflight", content)
            self.assertNotIn("tools/touch", content)


if __name__ == "__main__":
    unittest.main()
