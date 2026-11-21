#!/usr/bin/env python3
"""Unit tests for Lynx aux camera (IMX355 ultrawide + GC02M1 macro) preflight."""

import ast
import json
from pathlib import Path
import subprocess
import sys
import unittest

from lynx_aux_camera_preflight import (
    EXPECTED_COMPATIBLE,
    LIVE_COLLECT_SCRIPT,
    MACRO_AVDD_SUPPLY,
    MACRO_DOVDD_SUPPLY,
    MACRO_DVDD_SUPPLY,
    MACRO_EEPROM_ADDR,
    MACRO_I2C_ADDR,
    MACRO_I2C_BUS,
    MACRO_I2C_HZ,
    MACRO_MCLK_GPIO,
    MACRO_NODE,
    MACRO_RST_GPIO,
    MACRO_SENSOR_NAME,
    MACRO_SENINF_PORT,
    WIDE_AVDD_SUPPLY,
    WIDE_DOVDD_SUPPLY,
    WIDE_DVDD_SUPPLY,
    WIDE_EEPROM_ADDR,
    WIDE_I2C_ADDR,
    WIDE_I2C_BUS,
    WIDE_I2C_HZ,
    WIDE_MCLK_GPIO,
    WIDE_NODE,
    WIDE_RST_GPIO,
    WIDE_SENSOR_NAME,
    WIDE_SENINF_PORT,
    evaluate_aux_camera_preflight,
    validate_aux_camera_spec,
)

HERE = Path(__file__).resolve().parent
FIXTURES_DIR = HERE / "fixtures"
TOOL = HERE / "lynx_aux_camera_preflight.py"


def spec_doc() -> dict:
    """Return a valid board-spec document (from the bound fixture)."""
    return json.loads((FIXTURES_DIR / "aux-cameras-preflight-bound.json").read_text())


class TestExpectedConstants(unittest.TestCase):
    def test_wide_node_and_i2c_placement(self):
        self.assertEqual(WIDE_NODE, "sensor2@1a")
        self.assertEqual(WIDE_I2C_BUS, 2)
        self.assertEqual(WIDE_I2C_HZ, 400000)
        self.assertEqual(WIDE_I2C_ADDR, "0x1a")

    def test_wide_sensor_identity(self):
        self.assertEqual(EXPECTED_COMPATIBLE, "mediatek,imgsensor")
        self.assertEqual(WIDE_SENSOR_NAME, "imx355_mipi_raw_22823")
        self.assertTrue(WIDE_SENSOR_NAME.endswith("_22823"))

    def test_wide_gpio_and_rail_map(self):
        self.assertEqual(WIDE_MCLK_GPIO, 198)
        self.assertEqual(WIDE_RST_GPIO, 201)
        self.assertEqual(WIDE_AVDD_SUPPLY, "multi_reg_ldo4")
        self.assertEqual(WIDE_DVDD_SUPPLY, "multi_reg_ldo2")
        self.assertEqual(WIDE_DOVDD_SUPPLY, "multi_reg_ldo7")
        self.assertEqual(WIDE_EEPROM_ADDR, "0x51")
        self.assertEqual(WIDE_SENINF_PORT, 2)

    def test_macro_node_is_sensor4_not_sensor3(self):
        # The Round 6 queue guessed sensor3; the board DTS has sensor4@3d
        # and no sensor3 node at all.
        self.assertEqual(MACRO_NODE, "sensor4@3d")
        self.assertNotEqual(MACRO_NODE, "sensor3@3d")

    def test_macro_i2c_placement(self):
        self.assertEqual(MACRO_I2C_BUS, 9)
        self.assertEqual(MACRO_I2C_HZ, 1000000)
        self.assertEqual(MACRO_I2C_ADDR, "0x3d")

    def test_macro_sensor_identity(self):
        self.assertEqual(MACRO_SENSOR_NAME, "gc02m1_mipi_raw_22823")
        self.assertTrue(MACRO_SENSOR_NAME.endswith("_22823"))

    def test_macro_gpio_and_rail_map(self):
        self.assertEqual(MACRO_MCLK_GPIO, 197)
        self.assertEqual(MACRO_RST_GPIO, 200)
        self.assertEqual(MACRO_AVDD_SUPPLY, "multi_reg_ldo4")
        self.assertIsNone(MACRO_DVDD_SUPPLY)
        self.assertEqual(MACRO_DOVDD_SUPPLY, "multi_reg_ldo7")
        self.assertEqual(MACRO_EEPROM_ADDR, "0x52")
        self.assertEqual(MACRO_SENINF_PORT, 1)


class TestSpecValidation(unittest.TestCase):
    def test_valid_spec_passes(self):
        ok, failures = validate_aux_camera_spec(spec_doc())
        self.assertTrue(ok)
        self.assertEqual(failures, [])

    def test_corrupted_wide_node_rejected(self):
        doc = spec_doc()
        doc["wide"]["device_tree"]["node"] = "sensor3@1a"
        ok, failures = validate_aux_camera_spec(doc)
        self.assertFalse(ok)
        self.assertIn("wide_node_mismatch_sensor3@1a_True_sensor2@1a", failures)

    def test_corrupted_wide_i2c_placement_rejected(self):
        doc = spec_doc()
        doc["wide"]["device_tree"]["i2c_bus"] = 3
        doc["wide"]["device_tree"]["i2c_addr"] = "0x1b"
        ok, failures = validate_aux_camera_spec(doc)
        self.assertFalse(ok)
        self.assertIn("wide_i2c_bus_mismatch_3_vs_2", failures)
        self.assertIn("wide_i2c_addr_mismatch_0x1b_vs_0x1a", failures)

    def test_corrupted_wide_sensor_name_rejected(self):
        doc = spec_doc()
        doc["wide"]["device_tree"]["sensor_name"] = "imx415_mipi_raw_22823"
        ok, failures = validate_aux_camera_spec(doc)
        self.assertFalse(ok)
        self.assertIn(
            "wide_sensor_name_mismatch_imx415_mipi_raw_22823_vs_imx355_mipi_raw_22823",
            failures,
        )

    def test_corrupted_wide_rail_rejected(self):
        doc = spec_doc()
        doc["wide"]["rails"]["dvdd"] = "multi_reg_ldo3"
        ok, failures = validate_aux_camera_spec(doc)
        self.assertFalse(ok)
        self.assertIn(
            "wide_rail_dvdd_mismatch_multi_reg_ldo3_vs_multi_reg_ldo2",
            failures,
        )

    def test_corrupted_wide_gpio_rejected(self):
        doc = spec_doc()
        doc["wide"]["gpios"]["mclk"] = 197
        doc["wide"]["gpios"]["rst"] = 200
        ok, failures = validate_aux_camera_spec(doc)
        self.assertFalse(ok)
        self.assertIn("wide_mclk_mismatch_197_vs_198", failures)
        self.assertIn("wide_rst_mismatch_200_vs_201", failures)

    def test_corrupted_macro_node_rejected(self):
        doc = spec_doc()
        doc["macro"]["device_tree"]["node"] = "sensor3@3d"
        ok, failures = validate_aux_camera_spec(doc)
        self.assertFalse(ok)
        self.assertIn("macro_node_mismatch_sensor3@3d_True_sensor4@3d", failures)

    def test_corrupted_macro_dvdd_rejected(self):
        # GC02M1 has no dvdd-supply in the DTS; asserting one is invalid.
        doc = spec_doc()
        doc["macro"]["rails"]["dvdd"] = "multi_reg_ldo2"
        ok, failures = validate_aux_camera_spec(doc)
        self.assertFalse(ok)
        self.assertIn("macro_rail_dvdd_mismatch_multi_reg_ldo2_vs_None", failures)


class TestEvaluator(unittest.TestCase):
    def test_bound_fixture_classifies_bound_ready(self):
        verdict = evaluate_aux_camera_preflight(spec_doc())
        self.assertTrue(verdict.is_valid)
        self.assertEqual(verdict.status, "BOUND_READY")
        self.assertTrue(verdict.wide_driver_bound)
        self.assertTrue(verdict.macro_driver_bound)

    def test_unbound_fixture_classifies_quiescent(self):
        data = json.loads(
            (FIXTURES_DIR / "aux-cameras-preflight-unbound.json").read_text()
        )
        verdict = evaluate_aux_camera_preflight(data)
        self.assertTrue(verdict.is_valid)
        self.assertEqual(verdict.status, "UNBOUND_QUIESCENT")

    def test_partial_enumeration_classification(self):
        data = spec_doc()
        data["runtime"]["macro"]["driver_bound"] = False
        verdict = evaluate_aux_camera_preflight(data)
        self.assertTrue(verdict.is_valid)
        self.assertEqual(verdict.status, "PARTIAL_ENUMERATED")
        self.assertIn("IMX355 ultrawide", verdict.summary)

    def test_missing_runtime_section_defaults_to_quiescent(self):
        data = spec_doc()
        del data["runtime"]
        verdict = evaluate_aux_camera_preflight(data)
        self.assertTrue(verdict.is_valid)
        self.assertEqual(verdict.status, "UNBOUND_QUIESCENT")

    def test_malformed_spec_fixture_rejected(self):
        data = json.loads(
            (FIXTURES_DIR / "aux-cameras-preflight-missing-dt.json").read_text()
        )
        verdict = evaluate_aux_camera_preflight(data)
        self.assertFalse(verdict.is_valid)
        self.assertEqual(verdict.status, "MALFORMED_SPEC")
        self.assertIn(
            "wide_sensor_name_mismatch_imx415_mipi_raw_22823_vs_imx355_mipi_raw_22823",
            verdict.failures,
        )

    def test_to_dict_contains_all_fields(self):
        verdict = evaluate_aux_camera_preflight(spec_doc())
        d = verdict.to_dict()
        for key in (
            "status", "is_valid", "wide_node_mapped", "wide_gpio_mapped",
            "wide_rails_mapped", "macro_node_mapped", "macro_gpio_mapped",
            "macro_rails_mapped", "wide_driver_bound", "macro_driver_bound",
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
        res = self.run_tool(str(FIXTURES_DIR / "aux-cameras-preflight-bound.json"))
        self.assertEqual(res.returncode, 0, res.stderr)
        payload = json.loads(res.stdout)
        self.assertEqual(payload["status"], "BOUND_READY")

    def test_cli_fixture_unbound_exit_zero(self):
        res = self.run_tool(str(FIXTURES_DIR / "aux-cameras-preflight-unbound.json"))
        self.assertEqual(res.returncode, 0, res.stderr)
        payload = json.loads(res.stdout)
        self.assertEqual(payload["status"], "UNBOUND_QUIESCENT")

    def test_cli_fixture_missing_dt_exit_one(self):
        res = self.run_tool(str(FIXTURES_DIR / "aux-cameras-preflight-missing-dt.json"))
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

    def test_no_unapproved_aux_local_calls(self):
        local_calls = HERE.parent / "local_calls"
        if not local_calls.is_dir():
            self.skipTest("local_calls directory absent")
        aux_rows = sorted(p.name for p in local_calls.rglob("*aux*"))
        # No aux-camera rows may exist in the agent catalog; the pre-existing
        # approved lynx_camera pair must stay untouched.
        self.assertEqual(aux_rows, [])
        camera_rows = sorted(p.name for p in local_calls.rglob("*camera*"))
        self.assertEqual(camera_rows, ["lynx_camera.json", "lynx_camera.sh"])
        for name in camera_rows:
            content = (local_calls / name).read_text()
            self.assertNotIn("lynx_aux_camera_preflight", content)


if __name__ == "__main__":
    unittest.main()
