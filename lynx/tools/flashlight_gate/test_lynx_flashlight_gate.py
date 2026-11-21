#!/usr/bin/env python3
"""Unit tests for the Lynx flashlight core & LED torch preflight gate (D22)."""

import ast
import json
from pathlib import Path
import subprocess
import sys
import unittest

from lynx_flashlight_gate import (
    EXPECTED_CHANNEL_NAME,
    EXPECTED_CORE_COMPATIBLE,
    EXPECTED_CORE_LABEL,
    EXPECTED_CORE_NODE_NAME,
    EXPECTED_CORE_PARENT,
    EXPECTED_ENDPOINT_CONSUMER,
    EXPECTED_ENDPOINT_LED,
    EXPECTED_LED_BUS,
    EXPECTED_LED_COOLING_CELLS,
    EXPECTED_LED_COMPATIBLE,
    EXPECTED_LED_NODE_NAME,
    EXPECTED_LED_REG,
    EXPECTED_NTC_ADC,
    EXPECTED_NTC_ADC_CHANNEL,
    EXPECTED_NTC_COMPATIBLE,
    EXPECTED_NTC_SENSOR_LABEL,
    LIVE_COLLECT_SCRIPT,
    evaluate_flashlight_gate,
    validate_flashlight_spec,
)

HERE = Path(__file__).resolve().parent
FIXTURES_DIR = HERE / "fixtures"
TOOL = HERE / "lynx_flashlight_gate.py"


def spec_doc() -> dict:
    """Return a valid board-spec document (from the torch-quiescent fixture)."""
    return json.loads((FIXTURES_DIR / "flashlight-gate-torch-quiescent.json").read_text())


class TestExpectedConstants(unittest.TestCase):
    def test_core_node_identity_matches_mt6983_dts(self):
        # mt6983.dts:13806-13808 (top-level node, parent /)
        self.assertEqual(EXPECTED_CORE_NODE_NAME, "flashlight_core")
        self.assertEqual(EXPECTED_CORE_LABEL, "flashlight_core")
        self.assertEqual(EXPECTED_CORE_PARENT, "root")

    def test_core_compatible_matches_mt6983_dts(self):
        self.assertEqual(EXPECTED_CORE_COMPATIBLE, "mediatek,flashlight_core")

    def test_led_node_identity_matches_vitamin_camera_dtsi(self):
        # cust_mt6983_vitamin_camera_v4l2.dtsi:312-334 (&i2c6)
        self.assertEqual(EXPECTED_LED_NODE_NAME, "lm3642@63")
        self.assertEqual(EXPECTED_LED_BUS, "i2c6")
        self.assertEqual(EXPECTED_LED_COMPATIBLE, "mediatek,lm3642_22823")
        self.assertEqual(EXPECTED_LED_REG, 0x63)
        self.assertEqual(EXPECTED_LED_COOLING_CELLS, 2)

    def test_single_channel_endpoint_pair(self):
        self.assertEqual(EXPECTED_CHANNEL_NAME, "flash@0")
        self.assertEqual(EXPECTED_ENDPOINT_LED, "fl_core_0")
        self.assertEqual(EXPECTED_ENDPOINT_CONSUMER, "flashlight_0")

    def test_ntc_sensor_identity_matches_vitamin_cam_thermal_dtsi(self):
        self.assertEqual(EXPECTED_NTC_SENSOR_LABEL, "cam_temp")
        self.assertEqual(EXPECTED_NTC_COMPATIBLE, "mediatek,cam-temp-vitamin")
        self.assertEqual(EXPECTED_NTC_ADC, "mt6373_adc")
        self.assertEqual(EXPECTED_NTC_ADC_CHANNEL, "AUXADC_VIN3")


class TestSpecValidation(unittest.TestCase):
    def test_valid_spec_passes(self):
        ok, failures = validate_flashlight_spec(spec_doc())
        self.assertTrue(ok, failures)
        self.assertEqual(failures, [])

    def test_missing_core_node_rejected(self):
        doc = spec_doc()
        doc["device_tree"]["core_node_present"] = False
        ok, failures = validate_flashlight_spec(doc)
        self.assertFalse(ok)
        self.assertIn("missing_flashlight_core_node_in_dt", failures)

    def test_corrupted_core_compatible_rejected(self):
        doc = spec_doc()
        doc["device_tree"]["core_compatible"] = "mediatek,torch"
        ok, failures = validate_flashlight_spec(doc)
        self.assertFalse(ok)
        self.assertTrue(any(f.startswith("core_compatible_mismatch") for f in failures))

    def test_corrupted_led_bus_rejected(self):
        doc = spec_doc()
        doc["device_tree"]["led_bus"] = "i2c2"
        ok, failures = validate_flashlight_spec(doc)
        self.assertFalse(ok)
        self.assertTrue(any(f.startswith("led_bus_mismatch") for f in failures))

    def test_corrupted_led_compatible_rejected(self):
        doc = spec_doc()
        doc["device_tree"]["led_compatible"] = "ti,lm3642"
        ok, failures = validate_flashlight_spec(doc)
        self.assertFalse(ok)
        self.assertTrue(any(f.startswith("led_compatible_mismatch") for f in failures))

    def test_corrupted_led_reg_rejected(self):
        doc = spec_doc()
        doc["device_tree"]["led_reg"] = 0x1a
        ok, failures = validate_flashlight_spec(doc)
        self.assertFalse(ok)
        self.assertTrue(any(f.startswith("led_reg_mismatch") for f in failures))

    def test_dual_channel_claim_rejected(self):
        doc = spec_doc()
        doc["device_tree"]["channel_count"] = 2
        ok, failures = validate_flashlight_spec(doc)
        self.assertFalse(ok)
        self.assertTrue(any(f.startswith("channel_count_mismatch") for f in failures))

    def test_corrupted_endpoint_pair_rejected(self):
        doc = spec_doc()
        doc["device_tree"]["endpoint_consumer"] = "flashlight_1"
        ok, failures = validate_flashlight_spec(doc)
        self.assertFalse(ok)
        self.assertTrue(any(f.startswith("endpoint_consumer_mismatch") for f in failures))

    def test_missing_ntc_sensor_rejected(self):
        doc = spec_doc()
        doc["device_tree"]["ntc_sensor_present"] = False
        ok, failures = validate_flashlight_spec(doc)
        self.assertFalse(ok)
        self.assertIn("missing_ntc_sensor_in_dt", failures)

    def test_corrupted_ntc_adc_rejected(self):
        doc = spec_doc()
        doc["device_tree"]["ntc_adc"] = "mt6375_adc"
        ok, failures = validate_flashlight_spec(doc)
        self.assertFalse(ok)
        self.assertTrue(any(f.startswith("ntc_adc_mismatch") for f in failures))

    def test_missing_device_tree_section_rejected(self):
        ok, failures = validate_flashlight_spec({})
        self.assertFalse(ok)
        self.assertIn("missing_flashlight_core_node_in_dt", failures)


class TestEvaluator(unittest.TestCase):
    def test_torch_quiescent_fixture(self):
        data = json.loads((FIXTURES_DIR / "flashlight-gate-torch-quiescent.json").read_text())
        v = evaluate_flashlight_gate(data)
        self.assertEqual(v.status, "TORCH_QUIESCENT")
        self.assertTrue(v.is_valid)
        self.assertTrue(v.led_driver_bound)
        self.assertTrue(v.torch_quiescent)

    def test_unbound_fixture_classifies_quiescent(self):
        data = json.loads((FIXTURES_DIR / "flashlight-gate-unbound.json").read_text())
        v = evaluate_flashlight_gate(data)
        self.assertEqual(v.status, "UNBOUND_QUIESCENT")
        self.assertTrue(v.is_valid)
        self.assertFalse(v.runtime_class_present)

    def test_partial_enumeration_classification(self):
        data = json.loads((FIXTURES_DIR / "flashlight-gate-torch-quiescent.json").read_text())
        data["runtime"]["led_driver_bound"] = False
        v = evaluate_flashlight_gate(data)
        self.assertEqual(v.status, "PARTIAL_ENUMERATED")
        self.assertTrue(v.is_valid)

    def test_torch_active_is_safety_anomaly(self):
        data = json.loads((FIXTURES_DIR / "flashlight-gate-torch-active.json").read_text())
        v = evaluate_flashlight_gate(data)
        self.assertEqual(v.status, "TORCH_ACTIVE")
        self.assertFalse(v.is_valid)
        self.assertIn("torch_not_quiescent", v.failures)

    def test_brightness_string_zero_is_quiescent(self):
        data = json.loads((FIXTURES_DIR / "flashlight-gate-torch-quiescent.json").read_text())
        data["runtime"]["led_brightness"] = "0"
        v = evaluate_flashlight_gate(data)
        self.assertEqual(v.status, "TORCH_QUIESCENT")
        self.assertTrue(v.torch_quiescent)

    def test_missing_runtime_section_defaults_to_unbound_quiescent(self):
        data = json.loads((FIXTURES_DIR / "flashlight-gate-torch-quiescent.json").read_text())
        del data["runtime"]
        v = evaluate_flashlight_gate(data)
        self.assertEqual(v.status, "UNBOUND_QUIESCENT")
        self.assertTrue(v.torch_quiescent)

    def test_malformed_spec_fixture_rejected(self):
        data = json.loads((FIXTURES_DIR / "flashlight-gate-missing-dt.json").read_text())
        v = evaluate_flashlight_gate(data)
        self.assertEqual(v.status, "MALFORMED_SPEC")
        self.assertFalse(v.is_valid)
        self.assertTrue(v.failures)

    def test_to_dict_contains_all_fields(self):
        v = evaluate_flashlight_gate(spec_doc())
        d = v.to_dict()
        for key in (
            "status", "is_valid", "core_node_mapped", "led_node_mapped",
            "single_channel_verified", "ntc_sensor_mapped",
            "runtime_class_present", "led_driver_bound", "torch_quiescent",
            "summary", "failures", "details",
        ):
            self.assertIn(key, d)


class TestCli(unittest.TestCase):
    def run_tool(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(TOOL), *args],
            capture_output=True, text=True, timeout=30,
        )

    def test_cli_fixture_torch_quiescent_exit_zero(self):
        res = self.run_tool(str(FIXTURES_DIR / "flashlight-gate-torch-quiescent.json"))
        self.assertEqual(res.returncode, 0, res.stderr)
        payload = json.loads(res.stdout)
        self.assertEqual(payload["status"], "TORCH_QUIESCENT")

    def test_cli_fixture_unbound_exit_zero(self):
        res = self.run_tool(str(FIXTURES_DIR / "flashlight-gate-unbound.json"))
        self.assertEqual(res.returncode, 0, res.stderr)
        payload = json.loads(res.stdout)
        self.assertEqual(payload["status"], "UNBOUND_QUIESCENT")

    def test_cli_fixture_missing_dt_exit_one(self):
        res = self.run_tool(str(FIXTURES_DIR / "flashlight-gate-missing-dt.json"))
        self.assertEqual(res.returncode, 1)
        payload = json.loads(res.stdout)
        self.assertEqual(payload["status"], "MALFORMED_SPEC")

    def test_cli_fixture_torch_active_exit_one(self):
        res = self.run_tool(str(FIXTURES_DIR / "flashlight-gate-torch-active.json"))
        self.assertEqual(res.returncode, 1)
        payload = json.loads(res.stdout)
        self.assertEqual(payload["status"], "TORCH_ACTIVE")

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

    def test_live_script_never_drives_the_torch(self):
        # Torch emission means writing brightness/delay; the collector must
        # not touch those attributes at all beyond reads.
        self.assertNotIn("/delay", LIVE_COLLECT_SCRIPT)
        self.assertNotIn("echo 1", LIVE_COLLECT_SCRIPT)
        self.assertNotIn("> /sys", LIVE_COLLECT_SCRIPT)

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
        # The preflight tool must not be wired into the agent catalog.
        for p in local_calls.rglob("*"):
            if not p.is_file():
                continue
            content = p.read_text()
            self.assertNotIn("lynx_flashlight_gate", content,
                             f"preflight referenced in {p.name}")
            self.assertNotIn("tools/flashlight_gate", content,
                             f"tools/flashlight_gate referenced in {p.name}")


if __name__ == "__main__":
    unittest.main()
