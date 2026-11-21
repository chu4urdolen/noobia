"""Offline fixture tests for the Lynx health collector.

Inject a fake runner everywhere: these tests never open a network
connection. They cover the normal path (mapping + units), missing source,
malformed output, timeout, total-budget exhaustion, no-fabrication on
partial data, CLI wiring, and the default SSH runner's argv shape.
"""

import io
import json
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lynx_health_collect as lhc  # noqa: E402
from portable_health import evaluate  # noqa: E402


HEALTHY_PHONE = {
    "schema": 2,
    "boot_id": "11111111-2222-3333-4444-555555555555",
    "uptime_seconds": 12345,
    "alpine_release": "3.22.1",
    "battery": {
        "capacity_percent": 72,
        "temperature_mC": 31500,
        "current_mA_signed": -210,
        "voltage_mV": 4020,
        "gauge_type": 42495,
        "read_errors": {"capacity": 0, "temperature": 0, "current": 0, "voltage": 0},
    },
    "thermal": {
        "max_mC": 41200,
        "zones_mC": {"cpu_0": 41200, "soc_max": 39000},
        "cooling_states": {"thermal-cpufreq-0": 0},
    },
    "services_running": {
        "lynx-health": True, "lynx-battery-reserve": True, "lynx-local-logs": True,
        "lynx-wifi": True, "lynx-dropbear": True, "lynx-maintenance": True,
        "lynx-time-sync": True, "lynx-power-history": True,
    },
    "wifi": {"carrier": True, "ipv4": "192.168.100.107/24"},
    "root_free_mib": 2100,
    "root_filesystem": {"source": "/dev/sdc85", "type": "ext4", "ext4_errors_count": 0},
    "power_log_bytes": 123456,
    "issues": [],
}


class FakeRunner:
    """Yields pre-programmed RunnerResults or raises pre-programmed exceptions."""

    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def __call__(self, command, timeout):
        self.calls.append((command, timeout))
        item = self.results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def ok_result(state=None, raw=None, stderr=""):
    stdout = raw if raw is not None else json.dumps(state)
    return lhc.RunnerResult(0, stdout, stderr)


class MappingTests(unittest.TestCase):
    def test_healthy_snapshot_shape_and_units(self):
        snap = lhc.collect(FakeRunner([ok_result(HEALTHY_PHONE)]), now="2026-11-21T00:00:00+00:00")
        self.assertEqual(snap["schema"], "portable-health/1")
        self.assertEqual(snap["host"], "lynx")
        self.assertEqual(snap["profile"], "lynx")
        self.assertEqual(snap["captured_at"], "2026-11-21T00:00:00Z")
        facts = snap["facts"]
        self.assertEqual(facts["battery"]["capacity_percent"], 72)
        self.assertEqual(facts["battery"]["current_ma"], -210)
        self.assertEqual(facts["battery"]["temperature_mc"], 31500)  # native milli-C
        self.assertEqual(facts["battery"]["gauge_read_errors"], 0)
        self.assertAlmostEqual(facts["thermal"]["max_c"], 41.2)
        self.assertNotIn("throttled", facts["thermal"])
        self.assertEqual(facts["storage"], {"free_mib": 2100, "fs_errors": 0})
        self.assertEqual(facts["network"], {"link_state": "wifi", "carrier": True,
                                            "ipv4": "192.168.100.107/24"})
        svcs = facts["services"]
        self.assertEqual(len(svcs["required"]), 8)
        self.assertEqual(svcs["failed"], [])
        self.assertEqual(set(svcs["running"]), set(svcs["required"]))
        self.assertEqual(snap["machine"], {"lynx": {}})
        self.assertTrue(snap["source"]["commands"][0]["ok"])

    def test_healthy_evaluates_ok(self):
        snap = lhc.collect(FakeRunner([ok_result(HEALTHY_PHONE)]))
        report = evaluate(snap)
        self.assertEqual(report["verdict"], "ok")

    def test_warn_bands(self):
        phone = json.loads(json.dumps(HEALTHY_PHONE))
        phone["battery"]["capacity_percent"] = 25
        phone["thermal"]["max_mC"] = 43500
        snap = lhc.collect(FakeRunner([ok_result(phone)]))
        report = evaluate(snap)
        by = {c["name"]: c for c in report["checks"]}
        self.assertEqual(by["battery"]["status"], "warn")
        self.assertEqual(by["thermal"]["status"], "warn")
        self.assertEqual(report["verdict"], "warn")

    def test_battery_below_reserve_is_fail(self):
        phone = json.loads(json.dumps(HEALTHY_PHONE))
        phone["battery"]["capacity_percent"] = 15
        snap = lhc.collect(FakeRunner([ok_result(phone)]))
        self.assertEqual(evaluate(snap)["verdict"], "fail")

    def test_gauge_read_errors_degrade_ok_to_warn(self):
        phone = json.loads(json.dumps(HEALTHY_PHONE))
        phone["battery"]["read_errors"]["capacity"] = 3
        snap = lhc.collect(FakeRunner([ok_result(phone)]))
        self.assertEqual(snap["facts"]["battery"]["gauge_read_errors"], 3)
        by = {c["name"]: c for c in evaluate(snap)["checks"]}
        self.assertEqual(by["battery"]["status"], "warn")

    def test_throttled_derived_from_cooling_state(self):
        phone = json.loads(json.dumps(HEALTHY_PHONE))
        phone["thermal"]["cooling_states"] = {"thermal-cpufreq-0": 5}
        snap = lhc.collect(FakeRunner([ok_result(phone)]))
        self.assertIs(snap["facts"]["thermal"]["throttled"], True)
        by = {c["name"]: c for c in evaluate(snap)["checks"]}
        self.assertEqual(by["thermal"]["status"], "warn")

    def test_wifi_down_maps_to_link_none_and_fail(self):
        phone = json.loads(json.dumps(HEALTHY_PHONE))
        phone["wifi"] = {"carrier": False, "ipv4": None}
        snap = lhc.collect(FakeRunner([ok_result(phone)]))
        self.assertEqual(snap["facts"]["network"]["link_state"], "none")
        by = {c["name"]: c for c in evaluate(snap)["checks"]}
        self.assertEqual(by["network"]["status"], "fail")

    def test_service_failure_is_fail(self):
        phone = json.loads(json.dumps(HEALTHY_PHONE))
        phone["services_running"]["lynx-time-sync"] = False
        snap = lhc.collect(FakeRunner([ok_result(phone)]))
        by = {c["name"]: c for c in evaluate(snap)["checks"]}
        self.assertEqual(by["services"]["status"], "fail")
        self.assertIn("lynx-time-sync", snap["facts"]["services"]["failed"])


class FailurePathTests(unittest.TestCase):
    def test_nonzero_exit_leaves_facts_absent_and_unknown(self):
        runner = FakeRunner([lhc.RunnerResult(1, "", "lynx-status: not installed")])
        snap = lhc.collect(runner)
        self.assertEqual(snap["facts"], {})
        self.assertFalse(snap["source"]["commands"][0]["ok"])
        self.assertIn("exit", snap["source"]["commands"][0]["error"])
        self.assertEqual(evaluate(snap)["verdict"], "unknown")

    def test_malformed_json_is_unknown_not_ok(self):
        runner = FakeRunner([ok_result(raw="this is not json")])
        snap = lhc.collect(runner)
        self.assertEqual(snap["facts"], {})
        self.assertIn("malformed", snap["source"]["commands"][0]["error"])
        self.assertEqual(evaluate(snap)["verdict"], "unknown")

    def test_json_array_is_rejected(self):
        runner = FakeRunner([ok_result(raw="[1,2,3]")])
        snap = lhc.collect(runner)
        self.assertEqual(snap["facts"], {})
        self.assertEqual(evaluate(snap)["verdict"], "unknown")

    def test_timeout_is_caught_and_reported(self):
        runner = FakeRunner([lhc.RunnerTimeout("/usr/local/bin/lynx-status")])
        snap = lhc.collect(runner)
        self.assertEqual(snap["facts"], {})
        self.assertIn("timeout", snap["source"]["commands"][0]["error"])
        self.assertEqual(evaluate(snap)["verdict"], "unknown")

    def test_total_budget_exhaustion_skips_the_command(self):
        runner = FakeRunner([ok_result(HEALTHY_PHONE)])
        snap = lhc.collect(runner, total_timeout=0)
        self.assertEqual(runner.calls, [])
        self.assertIn("budget exhausted", snap["source"]["commands"][0]["error"])
        self.assertEqual(evaluate(snap)["verdict"], "unknown")

    def test_per_cmd_timeout_capped_by_remaining_budget(self):
        runner = FakeRunner([lhc.RunnerTimeout("x")])
        lhc.collect(runner, per_cmd_timeout=15, total_timeout=2)
        self.assertLessEqual(runner.calls[0][1], 2.0)

    def test_partial_state_maps_only_present_sections(self):
        runner = FakeRunner([ok_result({"schema": 2, "battery": HEALTHY_PHONE["battery"],
                                       "issues": ["thermal_unavailable"]})])
        snap = lhc.collect(runner)
        self.assertIn("battery", snap["facts"])
        for name in ("thermal", "storage", "network", "services"):
            self.assertNotIn(name, snap["facts"])
        self.assertEqual(snap["source"]["issues"], ["thermal_unavailable"])
        by = {c["name"]: c for c in evaluate(snap)["checks"]}
        self.assertEqual(by["battery"]["status"], "ok")
        self.assertEqual(by["thermal"]["status"], "unknown")
        self.assertEqual(by["services"]["status"], "unknown")

    def test_none_and_string_values_are_not_fabricated(self):
        runner = FakeRunner([ok_result({
            "battery": {"capacity_percent": None, "temperature_mC": "41500",
                        "current_mA_signed": "nope",
                        "read_errors": {"capacity": 2, "temperature": None}},
            "thermal": {"max_mC": None, "cooling_states": {"c": "3"}},
            "wifi": {"carrier": "yes", "ipv4": 12},
        })])
        snap = lhc.collect(runner)
        facts = snap["facts"]
        # A section with nothing judgeable is absent, exactly like missing:
        # the evaluator treats absence and empty identically (unknown).
        for section in ("battery", "thermal", "network", "storage", "services"):
            self.assertNotIn(section, facts)
        self.assertEqual(evaluate(snap)["verdict"], "unknown")

    def test_output_is_capped(self):
        big = json.loads(json.dumps(HEALTHY_PHONE))
        big["pad"] = "x" * 20000
        runner = FakeRunner([ok_result(big)])
        snap = lhc.collect(runner, max_output=12000)
        self.assertTrue(snap["source"]["commands"][0]["truncated"])
        self.assertGreater(snap["source"]["commands"][0]["stdout_bytes"], 12000)


class CliTests(unittest.TestCase):
    def _patched_main(self, results, argv):
        original = lhc.make_ssh_runner
        lhc.make_ssh_runner = lambda ip, port: FakeRunner(results)
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = lhc.main(argv)
        finally:
            lhc.make_ssh_runner = original
        return code, buf.getvalue()

    def test_snapshot_mode_prints_snapshot_and_exits_zero(self):
        code, out = self._patched_main([ok_result(HEALTHY_PHONE)], [])
        self.assertEqual(code, 0)
        snap = json.loads(out)
        self.assertEqual(snap["schema"], "portable-health/1")

    def test_evaluate_mode_returns_verdict_exit(self):
        phone = json.loads(json.dumps(HEALTHY_PHONE))
        phone["battery"]["capacity_percent"] = 19
        code, out = self._patched_main([ok_result(phone)], ["--evaluate"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out)["verdict"], "fail")

    def test_evaluate_mode_unknown(self):
        code, out = self._patched_main([lhc.RunnerResult(1, "", "gone")], ["--evaluate"])
        self.assertEqual(code, 3)
        self.assertEqual(json.loads(out)["verdict"], "unknown")


class DefaultRunnerTests(unittest.TestCase):
    def test_argv_uses_pinned_key_port_and_batchmode(self):
        calls = []

        def fake_run(argv, **kwargs):
            calls.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, 0, stdout=b'{"schema":2}', stderr=b"")

        original = subprocess.run
        subprocess.run = fake_run
        try:
            runner = lhc.make_ssh_runner("192.168.100.107", 2222)
            result = runner("cmd", 10)
        finally:
            subprocess.run = original
        self.assertEqual(result.exit, 0)
        argv, kwargs = calls[0]
        self.assertIn("BatchMode=yes", argv)
        self.assertIn("-i", argv)
        self.assertTrue(argv[argv.index("-i") + 1].endswith("nexus_lynx_ed25519"))
        self.assertIn("-p", argv)
        self.assertEqual(argv[argv.index("-p") + 1], "2222")
        self.assertEqual(argv[-1], "cmd")
        self.assertEqual(kwargs.get("timeout"), 10)

    def test_timeout_mapped_to_runner_timeout(self):
        def boom(argv, **kwargs):
            raise subprocess.TimeoutExpired(argv, 1)

        original = subprocess.run
        subprocess.run = boom
        try:
            runner = lhc.make_ssh_runner("192.168.100.107", 2222)
            with self.assertRaises(lhc.RunnerTimeout):
                runner("cmd", 1)
        finally:
            subprocess.run = original


if __name__ == "__main__":
    unittest.main()
