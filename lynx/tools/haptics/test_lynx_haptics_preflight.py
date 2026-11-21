#!/usr/bin/env python3
"""Unit tests for the Lynx haptics (LRA) preflight gate (Round 7, item D21)."""

import ast
import json
from pathlib import Path
import subprocess
import sys
import unittest

from lynx_haptics_preflight import (
    EXPECTED_COMPATIBLE,
    EXPECTED_NODE_LABEL,
    EXPECTED_NODE_NAME,
    EXPECTED_PARENT,
    EXPECTED_VIB_LIMIT,
    EXPECTED_VIB_TIMER,
    EXPECTED_VIB_VOL,
    LIVE_COLLECT_SCRIPT,
    evaluate_haptics_preflight,
    validate_haptics_spec,
)

HERE = Path(__file__).resolve().parent
FIXTURES_DIR = HERE / "fixtures"
TOOL = HERE / "lynx_haptics_preflight.py"


def spec_doc() -> dict:
    """Return a valid board-spec document (from the bound fixture)."""
    return json.loads((FIXTURES_DIR / "haptics-preflight-bound.json").read_text())


class TestExpectedConstants(unittest.TestCase):
    def test_node_identity_matches_board_dts(self):
        self.assertEqual(EXPECTED_NODE_NAME, "vibrator@0")
        self.assertEqual(EXPECTED_NODE_LABEL, "vibrator0")
        self.assertEqual(EXPECTED_PARENT, "odm")

    def test_compatible_matches_board_dts(self):
        self.assertEqual(EXPECTED_COMPATIBLE, "mediatek,vibrator")

    def test_waveform_params_match_board_dts(self):
        # oplus6983_22823.dts: vib_timer = <25>; vib_limit = <9>; vib_vol = <9>;
        self.assertEqual(EXPECTED_VIB_TIMER, 25)
        self.assertEqual(EXPECTED_VIB_LIMIT, 9)
        self.assertEqual(EXPECTED_VIB_VOL, 9)


class TestSpecValidation(unittest.TestCase):
    def test_valid_spec_passes(self):
        ok, failures = validate_haptics_spec(spec_doc())
        self.assertTrue(ok, failures)
        self.assertEqual(failures, [])

    def test_missing_vibrator_node_rejected(self):
        doc = spec_doc()
        doc["device_tree"]["vibrator_node_present"] = False
        ok, failures = validate_haptics_spec(doc)
        self.assertFalse(ok)
        self.assertIn("missing_vibrator_node_in_dt", failures)

    def test_corrupted_node_name_rejected(self):
        doc = spec_doc()
        doc["device_tree"]["node_name"] = "vibrator@1"
        ok, failures = validate_haptics_spec(doc)
        self.assertFalse(ok)
        self.assertTrue(any(f.startswith("node_name_mismatch") for f in failures))

    def test_corrupted_parent_node_rejected(self):
        doc = spec_doc()
        doc["device_tree"]["parent_node"] = "soc"
        ok, failures = validate_haptics_spec(doc)
        self.assertFalse(ok)
        self.assertTrue(any(f.startswith("parent_node_mismatch") for f in failures))

    def test_corrupted_compatible_rejected(self):
        doc = spec_doc()
        doc["device_tree"]["compatible"] = "mediatek,goodix"
        ok, failures = validate_haptics_spec(doc)
        self.assertFalse(ok)
        self.assertTrue(any(f.startswith("compatible_mismatch") for f in failures))

    def test_corrupted_vib_timer_rejected(self):
        doc = spec_doc()
        doc["device_tree"]["vib_timer"] = 50
        ok, failures = validate_haptics_spec(doc)
        self.assertFalse(ok)
        self.assertTrue(any(f.startswith("vib_timer_mismatch") for f in failures))

    def test_corrupted_vib_limit_rejected(self):
        doc = spec_doc()
        doc["device_tree"]["vib_limit"] = 12
        ok, failures = validate_haptics_spec(doc)
        self.assertFalse(ok)
        self.assertTrue(any(f.startswith("vib_limit_mismatch") for f in failures))

    def test_corrupted_vib_vol_rejected(self):
        doc = spec_doc()
        doc["device_tree"]["vib_vol"] = 3
        ok, failures = validate_haptics_spec(doc)
        self.assertFalse(ok)
        self.assertTrue(any(f.startswith("vib_vol_mismatch") for f in failures))

    def test_missing_device_tree_section_rejected(self):
        ok, failures = validate_haptics_spec({})
        self.assertFalse(ok)
        self.assertIn("missing_vibrator_node_in_dt", failures)


class TestEvaluator(unittest.TestCase):
    def test_bound_fixture_classifies_bound_quiescent(self):
        data = json.loads((FIXTURES_DIR / "haptics-preflight-bound.json").read_text())
        v = evaluate_haptics_preflight(data)
        self.assertEqual(v.status, "BOUND_QUIESCENT")
        self.assertTrue(v.is_valid)
        self.assertTrue(v.vibrator_driver_bound)
        self.assertTrue(v.actuator_quiescent)

    def test_unbound_fixture_classifies_quiescent(self):
        data = json.loads((FIXTURES_DIR / "haptics-preflight-unbound.json").read_text())
        v = evaluate_haptics_preflight(data)
        self.assertEqual(v.status, "UNBOUND_QUIESCENT")
        self.assertTrue(v.is_valid)
        self.assertFalse(v.vibrator_class_present)

    def test_partial_enumeration_classification(self):
        data = json.loads((FIXTURES_DIR / "haptics-preflight-bound.json").read_text())
        data["runtime"]["vibrator_driver_bound"] = False
        v = evaluate_haptics_preflight(data)
        self.assertEqual(v.status, "PARTIAL_ENUMERATED")
        self.assertTrue(v.is_valid)

    def test_active_pulse_is_safety_anomaly(self):
        data = json.loads((FIXTURES_DIR / "haptics-preflight-active-pulse.json").read_text())
        v = evaluate_haptics_preflight(data)
        self.assertEqual(v.status, "ACTIVE_PULSE")
        self.assertFalse(v.is_valid)
        self.assertIn("actuator_not_quiescent", v.failures)

    def test_state_string_zero_is_quiescent(self):
        data = json.loads((FIXTURES_DIR / "haptics-preflight-bound.json").read_text())
        data["runtime"]["vibrator_state"] = "0"
        v = evaluate_haptics_preflight(data)
        self.assertEqual(v.status, "BOUND_QUIESCENT")
        self.assertTrue(v.actuator_quiescent)

    def test_missing_runtime_section_defaults_to_quiescent(self):
        data = json.loads((FIXTURES_DIR / "haptics-preflight-bound.json").read_text())
        del data["runtime"]
        v = evaluate_haptics_preflight(data)
        self.assertEqual(v.status, "UNBOUND_QUIESCENT")
        self.assertTrue(v.actuator_quiescent)

    def test_malformed_spec_fixture_rejected(self):
        data = json.loads((FIXTURES_DIR / "haptics-preflight-missing-dt.json").read_text())
        v = evaluate_haptics_preflight(data)
        self.assertEqual(v.status, "MALFORMED_SPEC")
        self.assertFalse(v.is_valid)
        self.assertTrue(v.failures)

    def test_to_dict_contains_all_fields(self):
        v = evaluate_haptics_preflight(spec_doc())
        d = v.to_dict()
        for key in (
            "status", "is_valid", "node_mapped", "compatible_mapped",
            "waveform_params_mapped", "vibrator_class_present",
            "vibrator_driver_bound", "actuator_quiescent",
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
        res = self.run_tool(str(FIXTURES_DIR / "haptics-preflight-bound.json"))
        self.assertEqual(res.returncode, 0, res.stderr)
        payload = json.loads(res.stdout)
        self.assertEqual(payload["status"], "BOUND_QUIESCENT")

    def test_cli_fixture_unbound_exit_zero(self):
        res = self.run_tool(str(FIXTURES_DIR / "haptics-preflight-unbound.json"))
        self.assertEqual(res.returncode, 0, res.stderr)
        payload = json.loads(res.stdout)
        self.assertEqual(payload["status"], "UNBOUND_QUIESCENT")

    def test_cli_fixture_missing_dt_exit_one(self):
        res = self.run_tool(str(FIXTURES_DIR / "haptics-preflight-missing-dt.json"))
        self.assertEqual(res.returncode, 1)
        payload = json.loads(res.stdout)
        self.assertEqual(payload["status"], "MALFORMED_SPEC")

    def test_cli_fixture_active_pulse_exit_one(self):
        res = self.run_tool(str(FIXTURES_DIR / "haptics-preflight-active-pulse.json"))
        self.assertEqual(res.returncode, 1)
        payload = json.loads(res.stdout)
        self.assertEqual(payload["status"], "ACTIVE_PULSE")

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

    def test_live_script_never_writes_vibrator_state(self):
        # Driving the actuator means writing state/delay/brightness; the
        # collector must not touch those attributes at all beyond reads.
        self.assertNotIn("/delay", LIVE_COLLECT_SCRIPT)
        self.assertNotIn("echo 1", LIVE_COLLECT_SCRIPT)

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
        # The preflight tool must not be wired into the agent catalog,
        # whatever approved haptic entries already exist there.
        for p in local_calls.rglob("*"):
            if not p.is_file():
                continue
            content = p.read_text()
            self.assertNotIn("lynx_haptics_preflight", content,
                             f"preflight referenced in {p.name}")
            self.assertNotIn("tools/haptics", content,
                             f"tools/haptics referenced in {p.name}")


if __name__ == "__main__":
    unittest.main()
