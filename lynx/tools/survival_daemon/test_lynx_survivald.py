#!/usr/bin/env python3
"""Unit tests for the Lynx autonomous survival & power daemon (D26)."""

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

from lynx_survivald import (
    CRITICAL_BATTERY_SHUTDOWN_PCT,
    DEFAULT_STATE_FILE,
    EMERGENCY_SHUTDOWN,
    EMERGENCY_SKIN_TEMP_C,
    EMERGENCY_SOC_TEMP_C,
    FINAL_STOPPED,
    LOW_BATTERY_SUSPEND_PCT,
    LOW_POWER_SUSPEND,
    NOMINAL_OPERATION,
    POLICY_CHARGE_LIMIT_MA,
    POLL_INTERVAL_DEFAULT_S,
    THERMAL_THROTTLE_PAUSE_CHG,
    THROTTLE_SKIN_TEMP_C,
    THROTTLE_SOC_TEMP_C,
    WARN_BATTERY_PCT,
    evaluate_telemetry,
    simulate_poll_loop,
    validate_survivald_spec,
)

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
TOOL = HERE / "lynx_survivald.py"
INITD = HERE / "lynx-survivald.initd"
ENGINE = HERE.parent / "survival" / "lynx_survival_engine.py"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        capture_output=True,
        text=True,
        timeout=30,
    )


def engine_const(name: str):
    m = re.search(rf"^{name}\s*=\s*(\S+)", ENGINE.read_text(encoding="utf-8"), re.MULTILINE)
    assert m is not None, f"engine constant {name} not found"
    return m.group(1)


class TestThresholdsMatchB28Engine(unittest.TestCase):
    def test_battery_thresholds_match_engine(self):
        self.assertEqual(CRITICAL_BATTERY_SHUTDOWN_PCT, int(engine_const("CRITICAL_BATTERY_SHUTDOWN_PCT")))
        self.assertEqual(LOW_BATTERY_SUSPEND_PCT, int(engine_const("LOW_BATTERY_SUSPEND_PCT")))
        self.assertEqual(WARN_BATTERY_PCT, int(engine_const("WARN_BATTERY_PCT")))

    def test_thermal_thresholds_match_engine(self):
        self.assertEqual(EMERGENCY_SKIN_TEMP_C, float(engine_const("EMERGENCY_SKIN_TEMP_C")))
        self.assertEqual(THROTTLE_SKIN_TEMP_C, float(engine_const("THROTTLE_SKIN_TEMP_C")))
        self.assertEqual(EMERGENCY_SOC_TEMP_C, float(engine_const("EMERGENCY_SOC_TEMP_C")))
        self.assertEqual(THROTTLE_SOC_TEMP_C, float(engine_const("THROTTLE_SOC_TEMP_C")))

    def test_daemon_policy_constants(self):
        self.assertEqual(POLICY_CHARGE_LIMIT_MA, 500)
        self.assertEqual(POLL_INTERVAL_DEFAULT_S, 10.0)
        self.assertEqual(DEFAULT_STATE_FILE, "/tmp/lynx_survival_state.json")


class TestSpecValidation(unittest.TestCase):
    def test_valid_fixture_passes(self):
        self.assertTrue(validate_survivald_spec(load("survivald-nominal.json")).ok)

    def test_missing_engine_rejected(self):
        doc = load("survivald-nominal.json")
        del doc["engine"]
        self.assertFalse(validate_survivald_spec(doc).ok)

    def test_bad_interval_rejected(self):
        for bad in (0, 120, "10"):
            doc = load("survivald-nominal.json")
            doc["engine"]["poll_interval_s"] = bad
            self.assertFalse(validate_survivald_spec(doc).ok, bad)

    def test_negative_polls_rejected(self):
        doc = load("survivald-nominal.json")
        doc["engine"]["max_polls"] = -1
        self.assertFalse(validate_survivald_spec(doc).ok)

    def test_empty_series_rejected(self):
        doc = load("survivald-nominal.json")
        doc["telemetry_series"] = []
        self.assertFalse(validate_survivald_spec(doc).ok)

    def test_bad_signal_kind_rejected(self):
        doc = load("survivald-nominal.json")
        doc["signal"] = {"kind": "SIGKILL", "at_poll": 1}
        self.assertFalse(validate_survivald_spec(doc).ok)

    def test_unbounded_without_signal_rejected(self):
        doc = load("survivald-nominal.json")
        doc["engine"]["max_polls"] = 0
        doc["signal"] = None
        self.assertFalse(validate_survivald_spec(doc).ok)


class TestPolicyEvaluation(unittest.TestCase):
    def test_nominal_dispatches_schedutil_full_duty(self):
        d = evaluate_telemetry({"battery_pct": 80, "shell_temp_c": 33.0, "soc_max_temp_c": 42.0})
        self.assertEqual(d.policy_state, NOMINAL_OPERATION)
        self.assertEqual(d.status, "OK")
        gov = [a for a in d.actions if a.action == "set_cpu_governor"]
        self.assertEqual(gov[0].params["governor"], "schedutil")
        self.assertTrue(all(a.simulated for a in d.actions))

    def test_skin_throttle_dispatches_powersave_and_500ma(self):
        d = evaluate_telemetry({"battery_pct": 60, "shell_temp_c": 42.0, "soc_max_temp_c": 50.0})
        self.assertEqual(d.policy_state, THERMAL_THROTTLE_PAUSE_CHG)
        self.assertEqual(d.status, "WARN")
        gov = [a for a in d.actions if a.action == "set_cpu_governor"][0]
        self.assertEqual(gov.params["governor"], "powersave")
        lim = [a for a in d.actions if a.action == "limit_charge_current"][0]
        self.assertEqual(lim.params["limit_ma"], POLICY_CHARGE_LIMIT_MA)

    def test_die_throttle_band(self):
        d = evaluate_telemetry({"battery_pct": 60, "shell_temp_c": 30.0, "soc_max_temp_c": THROTTLE_SOC_TEMP_C})
        self.assertEqual(d.policy_state, THERMAL_THROTTLE_PAUSE_CHG)

    def test_reserve_band_triggers_suspend(self):
        d = evaluate_telemetry({"battery_pct": LOW_BATTERY_SUSPEND_PCT, "shell_temp_c": 30.0, "soc_max_temp_c": 40.0})
        self.assertEqual(d.policy_state, LOW_POWER_SUSPEND)
        susp = [a for a in d.actions if a.action == "trigger_suspend"]
        self.assertEqual(susp[0].params["mode"], "C_SLEEP")
        self.assertTrue(susp[0].simulated)

    def test_emergency_battery_triggers_graceful_sequence(self):
        d = evaluate_telemetry({"battery_pct": CRITICAL_BATTERY_SHUTDOWN_PCT, "shell_temp_c": 30.0, "soc_max_temp_c": 40.0})
        self.assertEqual(d.policy_state, EMERGENCY_SHUTDOWN)
        self.assertEqual(d.status, "CRITICAL")
        actions = [a.action for a in d.actions]
        self.assertIn("stop_agents", actions)
        self.assertIn("sync", actions)
        self.assertIn("poweroff", actions)

    def test_emergency_skin_cutoff(self):
        d = evaluate_telemetry({"battery_pct": 80, "shell_temp_c": EMERGENCY_SKIN_TEMP_C, "soc_max_temp_c": 50.0})
        self.assertEqual(d.policy_state, EMERGENCY_SHUTDOWN)

    def test_emergency_die_trip(self):
        d = evaluate_telemetry({"battery_pct": 80, "shell_temp_c": 30.0, "soc_max_temp_c": EMERGENCY_SOC_TEMP_C})
        self.assertEqual(d.policy_state, EMERGENCY_SHUTDOWN)

    def test_malformed_telemetry_is_emergency_not_crash(self):
        for bad in (None, [], "x", {"battery_pct": "high", "shell_temp_c": 30.0, "soc_max_temp_c": 40.0}):
            d = evaluate_telemetry(bad)
            self.assertEqual(d.policy_state, EMERGENCY_SHUTDOWN, bad)

    def test_boundary_just_below_trips_stay_nominal(self):
        d = evaluate_telemetry({"battery_pct": 26, "shell_temp_c": THROTTLE_SKIN_TEMP_C - 0.1, "soc_max_temp_c": THROTTLE_SOC_TEMP_C - 0.1})
        self.assertEqual(d.policy_state, NOMINAL_OPERATION)

    def test_decision_serializes_with_short_state(self):
        d = evaluate_telemetry({"battery_pct": 80, "shell_temp_c": 30.0, "soc_max_temp_c": 40.0})
        out = d.to_dict()
        self.assertEqual(out["state"], "NOMINAL")
        self.assertEqual(out["policy_state"], NOMINAL_OPERATION)
        self.assertIsInstance(out["actions"], list)


class TestSimulator(unittest.TestCase):
    def test_nominal_runs_all_polls_and_publishes(self):
        state = Path("/tmp/d26_nominal_state.json")
        if state.exists():
            state.unlink()
        doc = load("survivald-nominal.json")
        res = simulate_poll_loop(doc, state)
        self.assertEqual(res["final_state"], "NOMINAL")
        self.assertEqual(res["polls_executed"], 3)
        published = json.loads(state.read_text())
        self.assertEqual(published["state"], "NOMINAL")
        self.assertEqual(published["poll"], 3)
        state.unlink()

    def test_throttle_then_recover(self):
        doc = load("survivald-throttle-then-recover.json")
        res = simulate_poll_loop(doc, Path("/tmp/d26_throttle_state.json"))
        self.assertEqual(res["final_state"], "NOMINAL")
        first = [t for t in res["transcript"] if t["poll"] == 1][0]
        self.assertEqual(first["policy_state"], THERMAL_THROTTLE_PAUSE_CHG)
        gov = [a for a in first["actions"] if a["action"] == "set_cpu_governor"]
        self.assertEqual(gov[0]["params"]["governor"], "powersave")
        lim = [a for a in first["actions"] if a["action"] == "limit_charge_current"]
        self.assertEqual(lim[0]["params"]["limit_ma"], 500)

    def test_suspend_holds_state(self):
        doc = load("survivald-suspend.json")
        res = simulate_poll_loop(doc, Path("/tmp/d26_suspend_state.json"))
        self.assertEqual(res["final_state"], "LOW_POWER_SUSPEND")
        susp = [a for a in res["transcript"][-1]["actions"] if a["action"] == "trigger_suspend"]
        self.assertEqual(susp[0]["params"]["mode"], "C_SLEEP")

    def test_emergency_terminates_loop_early(self):
        doc = load("survivald-emergency.json")
        res = simulate_poll_loop(doc, Path("/tmp/d26_emergency_state.json"))
        self.assertEqual(res["final_state"], "EMERGENCY_SHUTDOWN")
        self.assertTrue(res["terminated_early"])
        self.assertEqual(res["polls_executed"], 2)
        terminal = [t for t in res["transcript"] if t.get("event") == "terminal"]
        self.assertEqual(len(terminal), 1)

    def test_signal_stop_publishes_stopped_state(self):
        doc = load("survivald-nominal.json")
        doc["engine"]["max_polls"] = 0
        doc["signal"] = {"kind": "SIGINT", "at_poll": 2}
        state = Path("/tmp/d26_signal_state.json")
        if state.exists():
            state.unlink()
        res = simulate_poll_loop(doc, state)
        self.assertEqual(res["final_state"], FINAL_STOPPED)
        self.assertEqual(res["polls_executed"], 1)
        published = json.loads(state.read_text())
        self.assertEqual(published["state"], "STOPPED_BY_SIGNAL")
        state.unlink()

    def test_unbounded_without_signal_raises(self):
        doc = load("survivald-nominal.json")
        doc["engine"]["max_polls"] = 0
        doc["signal"] = None
        with self.assertRaises(ValueError):
            simulate_poll_loop(doc, Path("/tmp/d26_never.json"))


class TestCli(unittest.TestCase):
    def test_fixture_nominal_exit_zero(self):
        r = run_cli("--validate", str(FIXTURES / "survivald-nominal.json"), "--state-file", "/tmp/d26_cli_state.json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('"verdict": "PASS"', r.stdout)

    def test_fixture_throttle_exit_zero(self):
        r = run_cli("--validate", str(FIXTURES / "survivald-throttle-then-recover.json"))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_fixture_suspend_exit_zero(self):
        r = run_cli("--validate", str(FIXTURES / "survivald-suspend.json"))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_fixture_emergency_exit_zero(self):
        r = run_cli("--validate", str(FIXTURES / "survivald-emergency.json"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("EMERGENCY_SHUTDOWN", r.stdout)

    def test_live_requires_double_flag(self):
        r = run_cli("--live")
        self.assertEqual(r.returncode, 2)
        self.assertIn("--allow-live", r.stderr)

    def test_no_args_help_exit_two(self):
        r = run_cli()
        self.assertEqual(r.returncode, 2)
        self.assertIn("usage", r.stdout)

    def test_malformed_spec_exit_one(self):
        bad = Path("/tmp/d26_bad_fixture.json")
        bad.write_text(json.dumps({"engine": {"poll_interval_s": 999, "max_polls": 1}, "telemetry_series": []}), encoding="utf-8")
        r = run_cli("--validate", str(bad))
        self.assertEqual(r.returncode, 1)
        self.assertIn("MALFORMED_SPEC", r.stderr)
        bad.unlink()


class TestSafetyBoundaries(unittest.TestCase):
    SRC = TOOL.read_text(encoding="utf-8")

    def test_no_os_module_at_all(self):
        self.assertNotIn("import os", self.SRC)
        self.assertNotIn("os.", self.SRC)

    def test_no_forbidden_runtime_tokens(self):
        for token in (
            "subprocess", "socket", "threading", "multiprocessing", "shutil",
            "urllib", "requests", "ctypes", "eval(", "exec(", "fork",
            "systemctl", "rm -rf", "curl ", "wget ", "iptables", "open(",
        ):
            self.assertNotIn(token, self.SRC, token)

    def test_no_real_shutdown_calls(self):
        self.assertIsNone(re.search(r"(?<![\w\"])poweroff\(", self.SRC))
        self.assertIsNone(re.search(r"(?<![\w\"])reboot\(", self.SRC))
        self.assertIsNone(re.search(r"(?<![\w.])sync\(", self.SRC))

    def test_actions_are_marked_simulated(self):
        self.assertGreater(self.SRC.count('"simulated": True'), 0)
        self.assertIn("simulated: bool = True", self.SRC)

    def test_broker_path_constant_only(self):
        occurrences = [m.start() for m in re.finditer(re.escape("/tmp/lynx_survival_state.json"), self.SRC)]
        self.assertEqual(len(occurrences), 1)

    def test_initd_is_staged_not_installed(self):
        text = INITD.read_text(encoding="utf-8")
        self.assertIn("after lynx-watchdogd", text)
        self.assertIn("STAGED", text)
        self.assertNotIn("systemctl", text)
        self.assertNotIn("install -", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
