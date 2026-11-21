#!/usr/bin/env python3
"""Unit tests for the Lynx MT6983 TOPRGU watchdog petting daemon (D25)."""

import ast
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

from lynx_watchdogd import (
    EXPECTED_BASE,
    EXPECTED_COMPATIBLES,
    EXPECTED_NODE,
    EXPECTED_REBOOT_MODE_COMPAT,
    EXPECTED_REBOOT_OFFSET,
    EXPECTED_SIZE,
    HEALTH_MAX_LOADAVG_1M,
    HEALTH_MIN_FREE_RAM_MB,
    MAGIC_STOP_CHAR,
    STATE_ABORTED_HEALTH_GATE,
    STATE_COMPLETED,
    STATE_STOPPED_BY_MAGIC_V,
    VALID_STATES,
    evaluate_health,
    make_pet_plan,
    simulate_pet_loop,
    validate_watchdogd_spec,
)

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
TOOL = HERE / "lynx_watchdogd.py"
INITD = HERE / "lynx-watchdogd.initd"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        capture_output=True,
        text=True,
        timeout=30,
    )


class TestExpectedConstants(unittest.TestCase):
    def test_node_and_compatible_match_b27_preflight(self):
        self.assertEqual(EXPECTED_NODE, "watchdog@1c007000")
        self.assertIn("mediatek,mt6983-wdt", EXPECTED_COMPATIBLES)
        self.assertIn("mediatek,mt6589-wdt", EXPECTED_COMPATIBLES)

    def test_mmio_base_size_reboot_mode(self):
        self.assertEqual(EXPECTED_BASE, "0x1c007000")
        self.assertEqual(EXPECTED_SIZE, "0x1000")
        self.assertEqual(EXPECTED_REBOOT_OFFSET, "0x24")
        self.assertEqual(EXPECTED_REBOOT_MODE_COMPAT, "syscon-reboot-mode")

    def test_magic_char_and_health_thresholds(self):
        self.assertEqual(MAGIC_STOP_CHAR, "V")
        self.assertEqual(HEALTH_MIN_FREE_RAM_MB, 50.0)
        self.assertEqual(HEALTH_MAX_LOADAVG_1M, 16.0)

    def test_valid_states_covered(self):
        self.assertIn(STATE_COMPLETED, VALID_STATES)
        self.assertIn(STATE_STOPPED_BY_MAGIC_V, VALID_STATES)
        self.assertIn(STATE_ABORTED_HEALTH_GATE, VALID_STATES)


class TestSpecValidation(unittest.TestCase):
    def test_valid_spec_passes(self):
        err = validate_watchdogd_spec(load("watchdogd-nominal.json"))
        self.assertTrue(err.ok, err.reasons)

    def test_corrupt_node_rejected(self):
        doc = load("watchdogd-nominal.json")
        doc["watchdog"]["node"] = "watchdog@1c007001"
        err = validate_watchdogd_spec(doc)
        self.assertFalse(err.ok)
        self.assertTrue(any("node" in r for r in err.reasons))

    def test_corrupt_compatible_rejected(self):
        doc = load("watchdogd-nominal.json")
        doc["watchdog"]["compatible"] = "generic,wdt"
        self.assertFalse(validate_watchdogd_spec(doc).ok)

    def test_corrupt_base_rejected(self):
        doc = load("watchdogd-nominal.json")
        doc["watchdog"]["base"] = "0xdeadbeef"
        self.assertFalse(validate_watchdogd_spec(doc).ok)

    def test_corrupt_size_rejected(self):
        doc = load("watchdogd-nominal.json")
        doc["watchdog"]["size"] = "0x2000"
        self.assertFalse(validate_watchdogd_spec(doc).ok)

    def test_corrupt_reboot_offset_rejected(self):
        doc = load("watchdogd-nominal.json")
        doc["watchdog"]["reboot_mode_offset"] = "0x00"
        self.assertFalse(validate_watchdogd_spec(doc).ok)

    def test_reboot_mode_compatible_rejected(self):
        doc = load("watchdogd-nominal.json")
        doc["watchdog"]["reboot_mode_compatible"] = "nope"
        self.assertFalse(validate_watchdogd_spec(doc).ok)

    def test_timeout_out_of_hw_range_rejected(self):
        for bad in (0, 33, -5, "30"):
            doc = load("watchdogd-nominal.json")
            doc["watchdog"]["timeout_s"] = bad
            self.assertFalse(validate_watchdogd_spec(doc).ok, bad)

    def test_interval_above_safe_window_rejected(self):
        doc = load("watchdogd-nominal.json")
        doc["petting"]["interval_s"] = 12.0
        self.assertFalse(validate_watchdogd_spec(doc).ok)

    def test_negative_cycles_rejected(self):
        doc = load("watchdogd-nominal.json")
        doc["petting"]["max_cycles"] = -1
        self.assertFalse(validate_watchdogd_spec(doc).ok)

    def test_wrong_magic_rejected(self):
        doc = load("watchdogd-nominal.json")
        doc["petting"]["magic"] = "X"
        self.assertFalse(validate_watchdogd_spec(doc).ok)

    def test_missing_sections_rejected(self):
        self.assertFalse(validate_watchdogd_spec({"petting": {"interval_s": 5, "max_cycles": 1}}).ok)
        self.assertFalse(validate_watchdogd_spec({"watchdog": load("watchdogd-nominal.json")["watchdog"]}).ok)
        self.assertFalse(validate_watchdogd_spec("not a dict").ok)


class TestHealthGate(unittest.TestCase):
    def test_healthy_probe_passes(self):
        rep = evaluate_health({"free_ram_mb": 128.0, "rootfs_writable": True, "loadavg_1m": 3.0})
        self.assertTrue(rep.ok, rep.reasons)

    def test_ram_boundary_rejected(self):
        self.assertFalse(evaluate_health({"free_ram_mb": HEALTH_MIN_FREE_RAM_MB, "rootfs_writable": True, "loadavg_1m": 1.0}).ok)
        self.assertTrue(evaluate_health({"free_ram_mb": HEALTH_MIN_FREE_RAM_MB + 0.1, "rootfs_writable": True, "loadavg_1m": 1.0}).ok)

    def test_loadavg_boundary_rejected(self):
        self.assertFalse(evaluate_health({"free_ram_mb": 200.0, "rootfs_writable": True, "loadavg_1m": HEALTH_MAX_LOADAVG_1M}).ok)
        self.assertTrue(evaluate_health({"free_ram_mb": 200.0, "rootfs_writable": True, "loadavg_1m": HEALTH_MAX_LOADAVG_1M - 0.1}).ok)

    def test_readonly_rootfs_rejected(self):
        self.assertFalse(evaluate_health({"free_ram_mb": 200.0, "rootfs_writable": False, "loadavg_1m": 1.0}).ok)

    def test_non_numeric_fields_rejected(self):
        self.assertFalse(evaluate_health({"free_ram_mb": "lots", "rootfs_writable": True, "loadavg_1m": "high"}).ok)

    def test_non_object_probe_rejected(self):
        for bad in (None, [], "probe"):
            self.assertFalse(evaluate_health(bad).ok)


class TestSimulator(unittest.TestCase):
    def test_nominal_completes_all_cycles(self):
        doc = load("watchdogd-nominal.json")
        res = simulate_pet_loop(make_pet_plan(doc), doc)
        self.assertEqual(res.final_state, STATE_COMPLETED)
        self.assertEqual(res.cycles_patted, 3)
        self.assertEqual([t["event"] for t in res.transcript if t["event"] == "pet"].count("pet"), 3)

    def test_magic_stop_writes_v_and_stops(self):
        doc = load("watchdogd-magic-stop.json")
        res = simulate_pet_loop(make_pet_plan(doc), doc)
        self.assertEqual(res.final_state, STATE_STOPPED_BY_MAGIC_V)
        self.assertEqual(res.cycles_patted, 1)
        stop = [t for t in res.transcript if t["event"] == "signal"]
        self.assertEqual(len(stop), 1)
        self.assertIn("'V'", stop[0]["action"])

    def test_sigint_also_magic_stops(self):
        doc = load("watchdogd-magic-stop.json")
        doc["signal"] = {"kind": "SIGINT", "at_cycle": 3}
        res = simulate_pet_loop(make_pet_plan(doc), doc)
        self.assertEqual(res.final_state, STATE_STOPPED_BY_MAGIC_V)
        self.assertEqual(res.cycles_patted, 2)

    def test_health_gate_aborts_without_petting(self):
        doc = load("watchdogd-health-gate.json")
        res = simulate_pet_loop(make_pet_plan(doc), doc)
        self.assertEqual(res.final_state, STATE_ABORTED_HEALTH_GATE)
        self.assertEqual(res.cycles_patted, 0)
        gate = [t for t in res.transcript if t["event"] == "gate-fail"]
        self.assertEqual(len(gate), 1)
        self.assertIn("WITHOUT magic V", gate[0]["action"])

    def test_late_gate_failure_pets_earlier_cycles(self):
        doc = load("watchdogd-nominal.json")
        doc["health_probes"][1]["loadavg_1m"] = 99.0
        res = simulate_pet_loop(make_pet_plan(doc), doc)
        self.assertEqual(res.final_state, STATE_ABORTED_HEALTH_GATE)
        self.assertEqual(res.cycles_patted, 1)

    def test_unbounded_without_signal_refused_offline(self):
        doc = load("watchdogd-nominal.json")
        doc["petting"]["max_cycles"] = 0
        doc["signal"] = None
        with self.assertRaises(ValueError):
            simulate_pet_loop(make_pet_plan(doc), doc)

    def test_bad_signal_kind_rejected(self):
        doc = load("watchdogd-nominal.json")
        doc["signal"] = {"kind": "SIGKILL", "at_cycle": 1}
        with self.assertRaises(ValueError):
            simulate_pet_loop(make_pet_plan(doc), doc)

    def test_result_serializes(self):
        doc = load("watchdogd-nominal.json")
        d = simulate_pet_loop(make_pet_plan(doc), doc).to_dict()
        self.assertEqual(d["final_state"], STATE_COMPLETED)
        self.assertEqual(d["cycles_patted"], 3)
        self.assertIsInstance(d["transcript"], list)
        self.assertIsNotNone(d["last_health"])


class TestCli(unittest.TestCase):
    def test_fixture_nominal_exit_zero(self):
        r = run_cli("--validate", str(FIXTURES / "watchdogd-nominal.json"), "--state-file", "/tmp/d25_state_nominal.json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('"final_state": "COMPLETED"', r.stdout)
        self.assertIn('"verdict": "PASS"', r.stdout)

    def test_fixture_magic_exit_zero(self):
        r = run_cli("--validate", str(FIXTURES / "watchdogd-magic-stop.json"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("STOPPED_BY_MAGIC_V", r.stdout)

    def test_fixture_health_gate_exit_zero(self):
        r = run_cli("--validate", str(FIXTURES / "watchdogd-health-gate.json"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("ABORTED_HEALTH_GATE", r.stdout)

    def test_fixture_malformed_exit_one(self):
        r = run_cli("--validate", str(FIXTURES / "watchdogd-malformed.json"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("MALFORMED_SPEC", r.stderr)

    def test_live_requires_double_flag(self):
        r = run_cli("--live")
        self.assertEqual(r.returncode, 2)
        self.assertIn("--allow-live", r.stderr)

    def test_no_args_prints_help_exit_two(self):
        r = run_cli()
        self.assertEqual(r.returncode, 2)
        self.assertIn("usage", r.stdout)

    def test_state_file_written(self):
        out = Path("/tmp/d25_state_check.json")
        if out.exists():
            out.unlink()
        r = run_cli("--validate", str(FIXTURES / "watchdogd-nominal.json"), "--state-file", str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(out.read_text())
        self.assertEqual(data["verdict"], "PASS")
        out.unlink()


class TestSafetyBoundaries(unittest.TestCase):
    SRC = TOOL.read_text(encoding="utf-8")
    TREE = ast.parse(SRC)

    ALLOWED_IMPORTS = {
        "__future__", "argparse", "json", "os", "pathlib", "signal", "sys",
        "time", "dataclasses", "typing",
    }
    FORBIDDEN_ATTRS = {
        "system", "popen", "execv", "execve", "execl", "spawnv", "spawnve",
        "fork", "forkpty", "kill", "nice", "setuid", "setgid",
    }
    LIVE_WRITE_FNS = {"run_live", "_live_magic_stop", "_install_stop_handlers"}
    DEVICE_OPEN_FNS = {"_live_open_watchdog"}
    FORBIDDEN_TOKENS = (
        "subprocess", "socket", "threading", "multiprocessing", "shutil",
        "urllib", "requests", "http.", "ctypes", "eval(", "exec(",
        "os.remove", "os.unlink", "os.rename", "os.rmdir", "rm -rf",
        "curl ", "wget ", "nc ", "iptables", "systemctl",
    )

    def _enclosing(self, node: ast.AST) -> str:
        for fn in ast.walk(self.TREE):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for child in ast.walk(fn):
                    if child is node:
                        return fn.name
        return "<module>"

    def test_imports_are_within_whitelist(self):
        for node in ast.walk(self.TREE):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertIn(alias.name.split(".")[0], self.ALLOWED_IMPORTS, alias.name)
            elif isinstance(node, ast.ImportFrom):
                self.assertIn((node.module or "").split(".")[0], self.ALLOWED_IMPORTS, node.module)

    def test_no_forbidden_runtime_calls(self):
        for node in ast.walk(self.TREE):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                if node.value.id == "os":
                    self.assertNotIn(node.attr, self.FORBIDDEN_ATTRS, f"forbidden os.{node.attr}")

    def test_no_forbidden_source_tokens(self):
        for token in self.FORBIDDEN_TOKENS:
            self.assertNotIn(token, self.SRC, token)

    def test_device_open_only_in_whitelisted_fn(self):
        for node in ast.walk(self.TREE):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "open" and isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                    self.assertIn(self._enclosing(node), self.DEVICE_OPEN_FNS, self._enclosing(node))

    def test_device_writes_only_in_whitelisted_fns(self):
        for node in ast.walk(self.TREE):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "write" and isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                    self.assertIn(self._enclosing(node), self.LIVE_WRITE_FNS, self._enclosing(node))

    def test_device_path_literal_scoped(self):
        for node in ast.walk(self.TREE):
            if isinstance(node, ast.Constant) and node.value == "/dev/watchdog":
                owner = self._enclosing(node)
                self.assertTrue(owner == "<module>" or owner in self.LIVE_WRITE_FNS | self.DEVICE_OPEN_FNS, owner)

    def test_no_bare_open_for_writes(self):
        pattern = re.compile(r"(?<![\w.])open\([^)]*['\"][wax+]['\"]")
        self.assertIsNone(pattern.search(self.SRC))

    def test_initd_is_staged_not_installed(self):
        text = INITD.read_text(encoding="utf-8")
        self.assertIn("provide watchdog", text)
        self.assertIn("before net", text)
        self.assertIn("STAGED", text)
        self.assertNotIn("systemctl", text)
        self.assertNotIn("mkinitrd", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
