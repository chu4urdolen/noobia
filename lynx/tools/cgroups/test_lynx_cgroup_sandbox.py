#!/usr/bin/env python3
"""Unit tests for the Lynx cgroups v2 agent sandbox (D27)."""

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

from lynx_cgroup_sandbox import (
    CPU_US_MAX,
    CPU_US_MIN,
    DEFAULT_CPU_PERIOD_US,
    DEFAULT_CPU_QUOTA_US,
    DEFAULT_CGROUP_NAME,
    DEFAULT_MEMORY_HIGH_BYTES,
    DEFAULT_MEMORY_MAX_BYTES,
    DEFAULT_OOM_GROUP,
    DEFAULT_STATE_FILE,
    ELEVATED_CPU_SOME_AVG3_MS,
    ELEVATED_MEMORY_SOME_AVG3_MS,
    MAX_QUOTA_PERIOD_RATIO,
    MEMORY_HIGH_MIN_BYTES,
    MEMORY_MAX_MAX_BYTES,
    MEMORY_MAX_MIN_BYTES,
    PressureParseError,
    PressureReading,
    SEVERITIES,
    SEVERITY_ELEVATED,
    SEVERITY_OK,
    SEVERITY_THRASHING,
    SpecError,
    THRASH_CPU_SOME_AVG3_MS,
    THRASH_MEMORY_SOME_AVG3_MS,
    assess_thrash,
    build_spec,
    parse_pressure,
    plan_actions,
    run_offline,
    validate_fixture,
)

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
TOOL = HERE / "lynx_cgroup_sandbox.py"
ARCH_DOC = HERE.parent.parent / "linux-port" / "docs" / "LYNX-AUTONOMY-ARCHITECTURE-20261121.md"

GOOD_PSI = (
    "some avg3=0.00 avg60=0.00 avg300=0.00 total=123\n"
    "full avg3=1.00 avg60=2.00 avg300=3.00 total=456"
)


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        capture_output=True,
        text=True,
        timeout=30,
    )


def reading(kind: str = "memory", some3: float = 0.0) -> PressureReading:
    return PressureReading(
        kind=kind, some_avg3=some3, some_avg60=0.0, some_avg300=0.0, some_total=0.0,
        full_avg3=0.0, full_avg60=0.0, full_avg300=0.0, full_total=0.0,
    )


def arch_value(pattern: str) -> str:
    text = ARCH_DOC.read_text(encoding="utf-8")
    m = re.search(pattern, text)
    assert m is not None, f"pattern {pattern!r} not found in B32 architecture doc"
    return m.group(1)


class TestConstantsMatchB32ArchDoc(unittest.TestCase):
    def test_memory_max_matches_arch_doc(self):
        self.assertEqual(DEFAULT_MEMORY_MAX_BYTES, int(arch_value(r"`memory\.max`:\s*`(\d+)`")))

    def test_memory_high_matches_arch_doc(self):
        self.assertEqual(DEFAULT_MEMORY_HIGH_BYTES, int(arch_value(r"`memory\.high`:\s*`(\d+)`")))

    def test_cpu_quota_matches_arch_doc(self):
        self.assertEqual(DEFAULT_CPU_QUOTA_US, int(arch_value(r"`cpu\.max`:\s*`(\d+)")))

    def test_cpu_period_matches_arch_doc(self):
        self.assertEqual(DEFAULT_CPU_PERIOD_US, int(arch_value(r"`cpu\.max`:\s*`\d+\s+(\d+)`")))

    def test_oom_group_matches_arch_doc(self):
        self.assertEqual(DEFAULT_OOM_GROUP, arch_value(r"`memory\.oom\.group`:\s*`(\d+)`"))

    def test_internal_consistency(self):
        self.assertTrue(MEMORY_HIGH_MIN_BYTES <= DEFAULT_MEMORY_HIGH_BYTES)
        self.assertTrue(MEMORY_MAX_MIN_BYTES <= DEFAULT_MEMORY_MAX_BYTES <= MEMORY_MAX_MAX_BYTES)
        self.assertTrue(CPU_US_MIN <= DEFAULT_CPU_QUOTA_US <= CPU_US_MAX)
        self.assertTrue(DEFAULT_CPU_QUOTA_US <= MAX_QUOTA_PERIOD_RATIO * DEFAULT_CPU_PERIOD_US)
        self.assertEqual(DEFAULT_CGROUP_NAME, "lynx-agent")


class TestSpecValidation(unittest.TestCase):
    def test_defaults_fill_missing(self):
        spec = build_spec({})
        self.assertEqual(spec.cgroup_name, DEFAULT_CGROUP_NAME)
        self.assertEqual(spec.memory_max_bytes, DEFAULT_MEMORY_MAX_BYTES)
        self.assertEqual(spec.memory_high_bytes, DEFAULT_MEMORY_HIGH_BYTES)
        self.assertEqual(spec.cpu_quota_us, DEFAULT_CPU_QUOTA_US)
        self.assertEqual(spec.cpu_period_us, DEFAULT_CPU_PERIOD_US)
        self.assertEqual(spec.oom_group, DEFAULT_OOM_GROUP)
        self.assertIsNone(spec.target_pid)

    def test_explicit_valid_spec(self):
        spec = build_spec({
            "memory_max_bytes": 268435456, "memory_high_bytes": 209715200,
            "cpu_quota_us": 50000, "cpu_period_us": 100000,
            "oom_group": "1", "target_pid": 1234,
        })
        self.assertEqual(spec.memory_max_bytes, 268435456)
        self.assertEqual(spec.target_pid, 1234)

    def test_name_uppercase_rejected(self):
        with self.assertRaises(SpecError) as ctx:
            build_spec({"cgroup_name": "Lynx-Agent"})
        self.assertIn("cgroup_name", " ".join(ctx.exception.reasons))

    def test_name_path_rejected(self):
        with self.assertRaises(SpecError):
            build_spec({"cgroup_name": "a/b"})

    def test_name_empty_rejected(self):
        with self.assertRaises(SpecError):
            build_spec({"cgroup_name": ""})

    def test_high_ge_max_rejected(self):
        with self.assertRaises(SpecError) as ctx:
            build_spec({"memory_max_bytes": 268435456, "memory_high_bytes": 301989888})
        self.assertTrue(any("memory_high_bytes" in r for r in ctx.exception.reasons))

    def test_max_below_min_rejected(self):
        with self.assertRaises(SpecError):
            build_spec({"memory_max_bytes": 8 * 1024 ** 2})

    def test_max_above_max_rejected(self):
        with self.assertRaises(SpecError):
            build_spec({"memory_max_bytes": 8 * 1024 ** 3})

    def test_quota_below_min_rejected(self):
        with self.assertRaises(SpecError):
            build_spec({"cpu_quota_us": 500})

    def test_ratio_exceeded_rejected(self):
        with self.assertRaises(SpecError) as ctx:
            build_spec({"cpu_quota_us": 1_000_000, "cpu_period_us": 1000})
        self.assertTrue(any("cpu_quota_us" in r for r in ctx.exception.reasons))

    def test_pid_zero_rejected(self):
        with self.assertRaises(SpecError):
            build_spec({"target_pid": 0})

    def test_pid_non_int_rejected(self):
        with self.assertRaises(SpecError):
            build_spec({"target_pid": "123"})

    def test_spec_not_dict_rejected(self):
        with self.assertRaises(SpecError):
            build_spec([1, 2, 3])

    def test_oom_group_invalid_rejected(self):
        with self.assertRaises(SpecError):
            build_spec({"oom_group": "5"})


class TestPressureParsing(unittest.TestCase):
    def test_valid_parses_both_lines(self):
        r = parse_pressure(GOOD_PSI, "memory")
        self.assertEqual(r.some_avg3, 0.0)
        self.assertEqual(r.full_avg3, 1.0)
        self.assertEqual(r.full_total, 456.0)

    def test_missing_full_line_rejected(self):
        with self.assertRaises(PressureParseError):
            parse_pressure("some avg3=1 avg60=1 avg300=1 total=1", "cpu")

    def test_missing_some_line_rejected(self):
        with self.assertRaises(PressureParseError):
            parse_pressure("full avg3=1 avg60=1 avg300=1 total=1", "cpu")

    def test_non_numeric_rejected(self):
        with self.assertRaises(PressureParseError):
            parse_pressure("some avg3=abc avg60=1 avg300=1 total=1\nfull avg3=1 avg60=1 avg300=1 total=1")

    def test_negative_rejected(self):
        with self.assertRaises(PressureParseError):
            parse_pressure("some avg3=-1 avg60=1 avg300=1 total=1\nfull avg3=1 avg60=1 avg300=1 total=1")

    def test_non_string_rejected(self):
        with self.assertRaises(PressureParseError):
            parse_pressure(12345, "cpu")

    def test_wrong_field_count_rejected(self):
        with self.assertRaises(PressureParseError):
            parse_pressure("some avg3=1 avg3=2 avg60=1 avg300=1 total=1\nfull avg3=1 avg60=1 avg300=1 total=1")


class TestThrashAssessment(unittest.TestCase):
    def test_ok_band(self):
        a = assess_thrash(reading("memory", 0.0), reading("cpu", 1.2))
        self.assertEqual(a.severity, SEVERITY_OK)
        self.assertFalse(a.memory_thrashing)
        self.assertFalse(a.cpu_thrashing)

    def test_memory_elevated(self):
        a = assess_thrash(reading("memory", 6.1), reading("cpu", 3.0))
        self.assertEqual(a.severity, SEVERITY_ELEVATED)

    def test_cpu_elevated(self):
        a = assess_thrash(reading("memory", 0.4), reading("cpu", 14.0))
        self.assertEqual(a.severity, SEVERITY_ELEVATED)

    def test_exact_memory_threshold_is_thrash(self):
        a = assess_thrash(reading("memory", THRASH_MEMORY_SOME_AVG3_MS), reading("cpu", 0.0))
        self.assertEqual(a.severity, SEVERITY_THRASHING)
        self.assertTrue(a.memory_thrashing)

    def test_exact_cpu_threshold_is_thrash(self):
        a = assess_thrash(reading("memory", 0.0), reading("cpu", THRASH_CPU_SOME_AVG3_MS))
        self.assertEqual(a.severity, SEVERITY_THRASHING)
        self.assertTrue(a.cpu_thrashing)

    def test_reasons_always_present(self):
        for some3 in (0.0, 6.1, 12.5):
            a = assess_thrash(reading("memory", some3), reading("cpu", 0.0))
            self.assertTrue(a.reasons)


class TestPlan(unittest.TestCase):
    def test_default_plan_order(self):
        plan = plan_actions(build_spec({}))
        self.assertEqual([a.action for a in plan],
                         ["ensure_group", "set_property", "set_property",
                          "set_property", "set_property"])

    def test_default_plan_values(self):
        plan = plan_actions(build_spec({}))
        targets = {a.target: a.params for a in plan}
        self.assertEqual(targets["/sys/fs/cgroup/lynx-agent/memory.max"]["value"], "536870912")
        self.assertEqual(targets["/sys/fs/cgroup/lynx-agent/memory.high"]["value"], "419430400")
        self.assertEqual(targets["/sys/fs/cgroup/lynx-agent/cpu.max"]["value"], "150000 100000")
        self.assertEqual(targets["/sys/fs/cgroup/lynx-agent/memory.oom.group"]["value"], "1")

    def test_pid_migration_appended_last(self):
        spec = build_spec({"target_pid": 1234})
        plan = plan_actions(spec)
        self.assertEqual(len(plan), 6)
        self.assertEqual(plan[-1].action, "migrate_pid")
        self.assertEqual(plan[-1].target, "/sys/fs/cgroup/lynx-agent/cgroup.procs")
        self.assertEqual(plan[-1].params["pid"], 1234)

    def test_all_actions_marked_simulated(self):
        plan = plan_actions(build_spec({"target_pid": 7}))
        for action in plan:
            self.assertTrue(action.simulated)
            self.assertTrue(action.to_dict()["simulated"])


class TestOfflineRun(unittest.TestCase):
    def _run(self, name: str, tag: str) -> int:
        state = Path(f"/tmp/d27_test_state_{tag}.json")
        if state.exists():
            state.unlink()
        rc = run_offline(FIXTURES / name, state)
        return rc, state

    def test_defaults_fixture_validates(self):
        rc, state = self._run("cgroup-sandbox-defaults.json", "defaults")
        self.assertEqual(rc, 0)
        doc = json.loads(state.read_text(encoding="utf-8"))
        self.assertEqual(doc["state"], "VALIDATED")
        self.assertEqual(doc["final_severity"], SEVERITY_ELEVATED)
        self.assertEqual(len(doc["polls"]), 3)

    def test_thrashing_fixture_validates(self):
        rc, state = self._run("cgroup-sandbox-thrashing-pid.json", "thrash")
        self.assertEqual(rc, 0)
        doc = json.loads(state.read_text(encoding="utf-8"))
        self.assertEqual(doc["final_severity"], SEVERITY_THRASHING)
        self.assertEqual(doc["plan"][-1]["action"], "migrate_pid")

    def test_rejected_fixture_validates(self):
        rc, state = self._run("cgroup-sandbox-spec-rejected.json", "rejected")
        self.assertEqual(rc, 0)
        doc = json.loads(state.read_text(encoding="utf-8"))
        self.assertEqual(doc["state"], "SPEC_REJECTED")
        self.assertTrue(any("memory_high_bytes" in r for r in doc["reasons"]))

    def test_tampered_severity_fails(self):
        doc = load("cgroup-sandbox-defaults.json")
        doc["pressure_series"][0]["expected_severity"] = SEVERITY_THRASHING
        state = Path("/tmp/d27_test_state_tampered.json")
        fixture = Path("/tmp/d27_test_tampered.json")
        fixture.write_text(json.dumps(doc), encoding="utf-8")
        self.assertEqual(run_offline(fixture, state), 1)

    def test_missing_platform_fails(self):
        doc = load("cgroup-sandbox-defaults.json")
        del doc["platform"]
        with self.assertRaises(SpecError):
            validate_fixture(doc)

    def test_empty_series_in_plan_mode_fails(self):
        doc = load("cgroup-sandbox-defaults.json")
        doc["pressure_series"] = []
        with self.assertRaises(SpecError):
            validate_fixture(doc)

    def test_unknown_severity_fails(self):
        doc = load("cgroup-sandbox-defaults.json")
        doc["pressure_series"][0]["expected_severity"] = "MEH"
        with self.assertRaises(SpecError):
            validate_fixture(doc)


class TestCli(unittest.TestCase):
    def test_fixture_defaults_exit_zero(self):
        proc = run_cli("--validate", str(FIXTURES / "cgroup-sandbox-defaults.json"))
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_fixture_thrashing_exit_zero(self):
        proc = run_cli("--validate", str(FIXTURES / "cgroup-sandbox-thrashing-pid.json"))
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_fixture_rejected_exit_zero(self):
        proc = run_cli("--validate", str(FIXTURES / "cgroup-sandbox-spec-rejected.json"))
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_live_requires_double_flag(self):
        proc = run_cli("--live")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("REFUSED", proc.stderr)

    def test_no_args_help_exit_two(self):
        proc = run_cli()
        self.assertEqual(proc.returncode, 2)
        self.assertIn("usage:", proc.stdout)

    def test_missing_fixture_exit_one(self):
        proc = run_cli("--validate", "/no/such/fixture.json")
        self.assertEqual(proc.returncode, 1)

    def test_malformed_json_exit_one(self):
        bad = Path("/tmp/d27_test_bad_fixture.json")
        bad.write_text("{ not json", encoding="utf-8")
        proc = run_cli("--validate", str(bad))
        self.assertEqual(proc.returncode, 1)


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

    def test_no_path_mutations(self):
        for token in (".mkdir(", ".makedirs(", ".unlink(", ".rmdir(",
                      ".chmod(", ".chown(", ".symlink(", ".rename("):
            self.assertNotIn(token, self.SRC, token)

    def test_actions_are_marked_simulated(self):
        self.assertIn('"simulated": self.simulated', self.SRC)
        self.assertIn("simulated: bool = True", self.SRC)

    def test_broker_path_constant_only(self):
        occurrences = [m.start() for m in re.finditer(re.escape("/tmp/lynx_cgroup_state.json"), self.SRC)]
        self.assertEqual(len(occurrences), 1)
        self.assertIn("DEFAULT_STATE_FILE", self.SRC)

    def test_no_initd_staged(self):
        # D27 queue ships no initd; the lynx-cgroups service wraps this tool
        # in a later round and is covered by the D28 service-tree validator.
        self.assertFalse(any(p.suffix == ".initd" for p in HERE.iterdir()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
