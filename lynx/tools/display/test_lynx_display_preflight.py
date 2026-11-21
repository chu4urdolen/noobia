#!/usr/bin/env python3
"""Unit tests for Lynx AMOLED display & panel bring-up preflight."""

import ast
import json
from pathlib import Path
import subprocess
import sys
import unittest

from lynx_display_preflight import (
    ACTIVE_PANEL_MODULE,
    EXPECTED_1P8_SUPPLY,
    EXPECTED_3P0_SUPPLY,
    EXPECTED_ACTIVE_PANEL_COMPATIBLE,
    EXPECTED_AOD_GPIO,
    EXPECTED_BACKLIGHT_LABEL,
    EXPECTED_BACKLIGHT_LED_BITS,
    EXPECTED_BACKLIGHT_MAX_BRIGHTNESS,
    EXPECTED_BACKLIGHT_PWM_CHANNEL,
    EXPECTED_PANEL_CHANNEL_ADC,
    EXPECTED_PANEL_MODULES,
    EXPECTED_RESET_GPIO,
    EXPECTED_SECOND_SOURCE_PANEL_COMPATIBLE,
    EXPECTED_TE_OUT_GPIO,
    EXPECTED_TE_SWITCH_GPIO,
    EXPECTED_VDDR_ENABLE_GPIO,
    LIVE_COLLECT_SCRIPT,
    evaluate_display_preflight,
    validate_panel_spec,
)

HERE = Path(__file__).resolve().parent
FIXTURES_DIR = HERE / "fixtures"
TOOL = HERE / "lynx_display_preflight.py"


def spec_doc() -> dict:
    """Return a valid board-spec document (from the bound fixture)."""
    return json.loads((FIXTURES_DIR / "display-preflight-bound.json").read_text())


class TestExpectedConstants(unittest.TestCase):
    def test_active_panel_compatible_is_tianma_nt37705(self):
        self.assertEqual(EXPECTED_ACTIVE_PANEL_COMPATIBLE, "oplus22823,tm,nt37705,cmd")
        self.assertTrue(EXPECTED_ACTIVE_PANEL_COMPATIBLE.startswith("oplus22823"))

    def test_second_source_panel_compatible_is_boe_nt37701a(self):
        self.assertEqual(
            EXPECTED_SECOND_SOURCE_PANEL_COMPATIBLE, "oplus22021_boe_nt37701a_fhd_dsi_cmd"
        )

    def test_panel_gpio_map_matches_board_dts(self):
        self.assertEqual(EXPECTED_RESET_GPIO, 86)
        self.assertEqual(EXPECTED_VDDR_ENABLE_GPIO, 148)
        self.assertEqual(EXPECTED_TE_SWITCH_GPIO, 36)
        self.assertEqual(EXPECTED_TE_OUT_GPIO, 24)
        self.assertEqual(EXPECTED_AOD_GPIO, "mt6373_pio3")

    def test_panel_power_rails_match_board_dts(self):
        self.assertEqual(EXPECTED_1P8_SUPPLY, "mt6373_vrf18_aif")
        self.assertEqual(EXPECTED_3P0_SUPPLY, "mt6373_vmc")
        self.assertEqual(EXPECTED_PANEL_CHANNEL_ADC, "mt6373_adc AUXADC_VIN1 100K")

    def test_backlight_spec_matches_mtk_leds_node(self):
        self.assertEqual(EXPECTED_BACKLIGHT_LABEL, "lcd-backlight")
        self.assertEqual(EXPECTED_BACKLIGHT_MAX_BRIGHTNESS, 10239)
        self.assertEqual(EXPECTED_BACKLIGHT_LED_BITS, 13)
        self.assertEqual(EXPECTED_BACKLIGHT_PWM_CHANNEL, 1)

    def test_expected_panel_modules_derive_from_kernel_config(self):
        # Module names follow the CONFIG_DRM_PANEL_<NAME>=m symbol lowercasing.
        self.assertEqual(len(EXPECTED_PANEL_MODULES), 2)
        self.assertEqual(
            "CONFIG_DRM_PANEL_" + EXPECTED_PANEL_MODULES[0].upper(),
            "CONFIG_DRM_PANEL_OPLUS22823_TM_NT37705_FHD_DSI_CMD",
        )
        self.assertEqual(
            "CONFIG_DRM_PANEL_" + EXPECTED_PANEL_MODULES[1].upper(),
            "CONFIG_DRM_PANEL_OPLUS22021_BOE_NT37701A_FHD_DSI_CMD",
        )
        self.assertEqual(EXPECTED_PANEL_MODULES[0], ACTIVE_PANEL_MODULE)


class TestSpecValidation(unittest.TestCase):
    def test_valid_spec_passes(self):
        ok, failures = validate_panel_spec(spec_doc())
        self.assertTrue(ok)
        self.assertEqual(failures, [])

    def test_corrupted_reset_gpio_rejected(self):
        doc = spec_doc()
        doc["gpios"]["reset"] = 84
        ok, failures = validate_panel_spec(doc)
        self.assertFalse(ok)
        self.assertIn("gpio_reset_mismatch_84_vs_86", failures)

    def test_corrupted_3v0_rail_rejected(self):
        doc = spec_doc()
        doc["rails"]["p3v0_supply"] = "mt6373_vmch"
        ok, failures = validate_panel_spec(doc)
        self.assertFalse(ok)
        self.assertIn("rail_p3v0_supply_mismatch_mt6373_vmch_vs_mt6373_vmc", failures)

    def test_corrupted_backlight_max_brightness_rejected(self):
        doc = spec_doc()
        doc["backlight"]["max_brightness"] = 4095
        ok, failures = validate_panel_spec(doc)
        self.assertFalse(ok)
        self.assertIn("backlight_max_brightness_mismatch_4095_vs_10239", failures)

    def test_missing_dsi_host_rejected(self):
        doc = spec_doc()
        doc["device_tree"]["dsi_host_present"] = False
        ok, failures = validate_panel_spec(doc)
        self.assertFalse(ok)
        self.assertIn("missing_dsi0_host_node_in_dt", failures)

    def test_missing_second_source_compatible_rejected(self):
        doc = spec_doc()
        doc["device_tree"]["panel_compatible"] = EXPECTED_ACTIVE_PANEL_COMPATIBLE
        ok, failures = validate_panel_spec(doc)
        self.assertFalse(ok)
        self.assertIn(
            f"missing_second_source_compatible_{EXPECTED_SECOND_SOURCE_PANEL_COMPATIBLE}",
            failures,
        )

    def test_unexpected_panel_module_rejected(self):
        doc = spec_doc()
        doc["expected_modules"].append("oplus_display_panel")
        ok, failures = validate_panel_spec(doc)
        self.assertFalse(ok)
        self.assertIn("unexpected_panel_module_oplus_display_panel", failures)

    def test_missing_active_panel_module_rejected(self):
        doc = spec_doc()
        doc["expected_modules"] = ["oplus22021_boe_nt37701a_fhd_dsi_cmd"]
        ok, failures = validate_panel_spec(doc)
        self.assertFalse(ok)
        self.assertIn(f"missing_expected_panel_module_{ACTIVE_PANEL_MODULE}", failures)


class TestFixtures(unittest.TestCase):
    def test_fixture_bound_ready(self):
        data = json.loads((FIXTURES_DIR / "display-preflight-bound.json").read_text())
        verdict = evaluate_display_preflight(data)

        self.assertTrue(verdict.is_valid)
        self.assertEqual(verdict.status, "BOUND_READY")
        self.assertTrue(verdict.dsi_host_mapped)
        self.assertTrue(verdict.active_panel_mapped)
        self.assertTrue(verdict.second_source_panel_mapped)
        self.assertTrue(verdict.backlight_mapped)
        self.assertTrue(verdict.power_rails_mapped)
        self.assertTrue(verdict.gpio_map_mapped)
        self.assertTrue(verdict.panel_modules_expected)
        self.assertTrue(verdict.active_module_present)
        self.assertTrue(verdict.panel_driver_bound)
        self.assertEqual(verdict.failures, [])
        self.assertIn("bound and operational", verdict.summary)

    def test_fixture_unbound_quiescent(self):
        data = json.loads((FIXTURES_DIR / "display-preflight-unbound.json").read_text())
        verdict = evaluate_display_preflight(data)

        self.assertTrue(verdict.is_valid)
        self.assertEqual(verdict.status, "UNBOUND_QUIESCENT")
        self.assertTrue(verdict.dsi_host_mapped)
        self.assertTrue(verdict.active_panel_mapped)
        self.assertFalse(verdict.active_module_present)
        self.assertFalse(verdict.panel_driver_bound)
        self.assertIn("quiescent state", verdict.summary)

    def test_fixture_missing_dt_rejected(self):
        data = json.loads((FIXTURES_DIR / "display-preflight-missing-dt.json").read_text())
        verdict = evaluate_display_preflight(data)

        self.assertFalse(verdict.is_valid)
        self.assertEqual(verdict.status, "MALFORMED_SPEC")
        self.assertFalse(verdict.dsi_host_mapped)
        self.assertFalse(verdict.active_panel_mapped)
        self.assertIn("missing_dsi0_host_node_in_dt", verdict.failures)
        self.assertIn("missing_active_panel_compatible_oplus22823,tm,nt37705,cmd", verdict.failures)

    def test_partial_enumeration_classification(self):
        data = spec_doc()
        data["runtime"]["panel_driver_bound"] = True
        data["loaded_modules"] = []
        verdict = evaluate_display_preflight(data)
        self.assertTrue(verdict.is_valid)
        self.assertEqual(verdict.status, "PARTIAL_ENUMERATED")

    def test_missing_runtime_section_defaults_to_quiescent(self):
        data = spec_doc()
        del data["runtime"]
        del data["loaded_modules"]
        verdict = evaluate_display_preflight(data)
        self.assertTrue(verdict.is_valid)
        self.assertEqual(verdict.status, "UNBOUND_QUIESCENT")

    def test_to_dict_contains_all_fields(self):
        data = spec_doc()
        verdict = evaluate_display_preflight(data)
        d = verdict.to_dict()
        for key in (
            "status", "is_valid", "dsi_host_mapped", "active_panel_mapped",
            "second_source_panel_mapped", "backlight_mapped", "power_rails_mapped",
            "gpio_map_mapped", "panel_modules_expected", "active_module_present",
            "panel_driver_bound", "summary", "failures", "details",
        ):
            self.assertIn(key, d)


class TestCli(unittest.TestCase):
    def run_tool(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(TOOL), *args],
            capture_output=True, text=True, timeout=30,
        )

    def test_cli_fixture_bound_exit_zero(self):
        res = self.run_tool(str(FIXTURES_DIR / "display-preflight-bound.json"))
        self.assertEqual(res.returncode, 0, res.stderr)
        payload = json.loads(res.stdout)
        self.assertEqual(payload["status"], "BOUND_READY")

    def test_cli_fixture_unbound_exit_zero(self):
        res = self.run_tool(str(FIXTURES_DIR / "display-preflight-unbound.json"))
        self.assertEqual(res.returncode, 0, res.stderr)
        payload = json.loads(res.stdout)
        self.assertEqual(payload["status"], "UNBOUND_QUIESCENT")

    def test_cli_fixture_missing_dt_exit_one(self):
        res = self.run_tool(str(FIXTURES_DIR / "display-preflight-missing-dt.json"))
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
        lowered = LIVE_COLLECT_SCRIPT
        for token in forbidden:
            self.assertNotIn(token, lowered, f"forbidden token in live script: {token}")

    def test_live_script_uses_only_whitelisted_commands(self):
        allowed = {"cat", "ls", "find", "readlink", "tr", "echo", "for", "do", "done", "true", "sh"}
        import re
        commands = set(re.findall(r"^\s*([a-z_][a-z0-9_]*)\s", LIVE_COLLECT_SCRIPT, flags=re.MULTILINE))
        for cmd in commands:
            self.assertIn(cmd, allowed, f"non-whitelisted command in live script: {cmd}")

    def test_tool_imports_are_harmless(self):
        tree = ast.parse(TOOL.read_text())
        allowed_modules = {
            "dataclasses", "json", "pathlib", "subprocess", "sys", "typing", "argparse",
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
        display_rows = sorted(p.name for p in local_calls.rglob("*display*"))
        # Only the previously approved bounded status pair (commit 88a913f)
        # may exist in the agent catalog.
        self.assertEqual(display_rows, ["lynx_display_status.json", "lynx_display_status.sh"])
        # The preflight tool must not be wired into the agent catalog.
        for name in display_rows:
            content = (local_calls / name).read_text()
            self.assertNotIn("lynx_display_preflight", content)
            self.assertNotIn("tools/display", content)


if __name__ == "__main__":
    unittest.main()
