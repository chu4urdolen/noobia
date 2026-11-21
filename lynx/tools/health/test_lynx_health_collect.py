"""Offline fixture tests for the Lynx health collector.

Inject a fake runner everywhere: these tests never open a network
connection. They cover the normal path (mapping + units, all three
commands), machine-fact mapping (modem MD1, agent queue), missing source,
malformed output, timeout, runner-exception containment (Aria #103),
total-budget exhaustion, no-fabrication on partial data, CLI wiring, and
the default SSH runner's argv shape.
"""

import io
import json
import subprocess
import sys
import time
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

CELLULAR_OK = {
    "interface_ready": True,
    "validated": False,
    "evidence": {"ccci_node_count": 2, "md1_state_code": 0,
                 "modem_runtime_verified": False},
    "next": "modem startup and radio function remain unverified",
}

QUEUE_OK = {
    "counts": {"pending": 0, "running": 0, "done": 3},
    "oldest_pending_seconds": None,
    "stopped": False,
    "issues": [],
}


def ok_result(state=None, raw=None, stderr=""):
    stdout = raw if raw is not None else json.dumps(state)
    return lhc.RunnerResult(0, stdout, stderr)


DEFAULTS = {
    lhc.LINUX_STATUS_CMD: ok_result(HEALTHY_PHONE),
    lhc.CELLULAR_CMD: ok_result(CELLULAR_OK),
    lhc.AGENT_HEALTH_CMD: ok_result(QUEUE_OK),
}


class FakeRunner:
    """Command-keyed fake runner: returns pre-programmed results or raises.

    Unmentioned commands fall back to the healthy defaults, so tests can
    override just the command they are about. Optional per-command delays
    let budget-exhaustion tests run deterministically.
    """

    def __init__(self, by_command=None, delays=None):
        self.by_command = dict(DEFAULTS)
        if by_command:
            self.by_command.update(by_command)
        self.delays = dict(delays or {})
        self.calls = []

    def __call__(self, command, timeout):
        self.calls.append((command, timeout))
        delay = self.delays.get(command)
        if delay:
            time.sleep(delay)
        item = self.by_command[command]
        if isinstance(item, Exception):
            raise item
        return item


def by_name(report):
    return {c["name"]: c for c in report["checks"]}


class MappingTests(unittest.TestCase):
    def test_healthy_snapshot_shape_and_units(self):
        snap = lhc.collect(FakeRunner(), now="2026-11-21T00:00:00+00:00")
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
        # The two former unknown machine checks are now collected:
        self.assertEqual(snap["machine"], {"lynx": {"modem_md1_state": 0,
                                                    "pending": 0, "running": 0}})
        # All three commands ran and all succeeded:
        self.assertEqual(len(snap["source"]["commands"]), 3)
        self.assertTrue(all(c["ok"] for c in snap["source"]["commands"]))
        self.assertEqual([c["name"] for c in snap["source"]["commands"]],
                         [lhc.LINUX_STATUS_CMD, lhc.CELLULAR_CMD, lhc.AGENT_HEALTH_CMD])

    def test_healthy_evaluates_all_ok(self):
        snap = lhc.collect(FakeRunner())
        report = evaluate(snap)
        self.assertEqual(report["verdict"], "ok")
        checks = by_name(report)
        self.assertEqual(len(checks), 7)
        self.assertEqual(checks["lynx_modem"]["status"], "ok")
        self.assertEqual(checks["lynx_agent_queue"]["status"], "ok")

    def test_warn_bands(self):
        phone = json.loads(json.dumps(HEALTHY_PHONE))
        phone["battery"]["capacity_percent"] = 25
        phone["thermal"]["max_mC"] = 43500
        snap = lhc.collect(FakeRunner({lhc.LINUX_STATUS_CMD: ok_result(phone)}))
        checks = by_name(evaluate(snap))
        self.assertEqual(checks["battery"]["status"], "warn")
        self.assertEqual(checks["thermal"]["status"], "warn")
        self.assertEqual(evaluate(snap)["verdict"], "warn")

    def test_battery_below_reserve_is_fail(self):
        phone = json.loads(json.dumps(HEALTHY_PHONE))
        phone["battery"]["capacity_percent"] = 15
        snap = lhc.collect(FakeRunner({lhc.LINUX_STATUS_CMD: ok_result(phone)}))
        self.assertEqual(evaluate(snap)["verdict"], "fail")

    def test_gauge_read_errors_degrade_ok_to_warn(self):
        phone = json.loads(json.dumps(HEALTHY_PHONE))
        phone["battery"]["read_errors"]["capacity"] = 3
        snap = lhc.collect(FakeRunner({lhc.LINUX_STATUS_CMD: ok_result(phone)}))
        self.assertEqual(snap["facts"]["battery"]["gauge_read_errors"], 3)
        self.assertEqual(by_name(evaluate(snap))["battery"]["status"], "warn")

    def test_throttled_derived_from_cooling_state(self):
        phone = json.loads(json.dumps(HEALTHY_PHONE))
        phone["thermal"]["cooling_states"] = {"thermal-cpufreq-0": 5}
        snap = lhc.collect(FakeRunner({lhc.LINUX_STATUS_CMD: ok_result(phone)}))
        self.assertIs(snap["facts"]["thermal"]["throttled"], True)
        self.assertEqual(by_name(evaluate(snap))["thermal"]["status"], "warn")

    def test_wifi_down_maps_to_link_none_and_fail(self):
        phone = json.loads(json.dumps(HEALTHY_PHONE))
        phone["wifi"] = {"carrier": False, "ipv4": None}
        snap = lhc.collect(FakeRunner({lhc.LINUX_STATUS_CMD: ok_result(phone)}))
        self.assertEqual(snap["facts"]["network"]["link_state"], "none")
        self.assertEqual(by_name(evaluate(snap))["network"]["status"], "fail")

    def test_service_failure_is_fail(self):
        phone = json.loads(json.dumps(HEALTHY_PHONE))
        phone["services_running"]["lynx-time-sync"] = False
        snap = lhc.collect(FakeRunner({lhc.LINUX_STATUS_CMD: ok_result(phone)}))
        self.assertEqual(by_name(evaluate(snap))["services"]["status"], "fail")
        self.assertIn("lynx-time-sync", snap["facts"]["services"]["failed"])


class MachineMappingTests(unittest.TestCase):
    def test_modem_md1_zero_is_ok(self):
        snap = lhc.collect(FakeRunner())
        self.assertEqual(snap["machine"]["lynx"]["modem_md1_state"], 0)
        check = by_name(evaluate(snap))["lynx_modem"]
        self.assertEqual(check["status"], "ok")
        self.assertEqual(check["evidence"], {"modem_md1_state": 0})

    def test_modem_md1_nonzero_is_warn(self):
        cellular = json.loads(json.dumps(CELLULAR_OK))
        cellular["evidence"]["md1_state_code"] = 2
        snap = lhc.collect(FakeRunner({lhc.CELLULAR_CMD: ok_result(cellular)}))
        self.assertEqual(snap["machine"]["lynx"]["modem_md1_state"], 2)
        check = by_name(evaluate(snap))["lynx_modem"]
        self.assertEqual(check["status"], "warn")
        self.assertEqual(evaluate(snap)["verdict"], "warn")

    def test_modem_md1_null_stays_unknown(self):
        cellular = json.loads(json.dumps(CELLULAR_OK))
        cellular["evidence"]["md1_state_code"] = None
        snap = lhc.collect(FakeRunner({lhc.CELLULAR_CMD: ok_result(cellular)}))
        self.assertNotIn("modem_md1_state", snap["machine"]["lynx"])
        self.assertEqual(by_name(evaluate(snap))["lynx_modem"]["status"], "unknown")

    def test_modem_md1_bool_is_rejected(self):
        cellular = json.loads(json.dumps(CELLULAR_OK))
        cellular["evidence"]["md1_state_code"] = True
        snap = lhc.collect(FakeRunner({lhc.CELLULAR_CMD: ok_result(cellular)}))
        self.assertNotIn("modem_md1_state", snap["machine"]["lynx"])
        self.assertEqual(by_name(evaluate(snap))["lynx_modem"]["status"], "unknown")

    def test_queue_counts_and_oldest_mapped(self):
        queue = json.loads(json.dumps(QUEUE_OK))
        queue["counts"] = {"pending": 2, "running": 1, "done": 5}
        queue["oldest_pending_seconds"] = 30
        snap = lhc.collect(FakeRunner({lhc.AGENT_HEALTH_CMD: ok_result(queue)}))
        machine = snap["machine"]["lynx"]
        self.assertEqual(machine["pending"], 2)
        self.assertEqual(machine["running"], 1)
        self.assertEqual(machine["oldest_pending_seconds"], 30)
        check = by_name(evaluate(snap))["lynx_agent_queue"]
        self.assertEqual(check["status"], "ok")
        self.assertEqual(check["evidence"], {"pending": 2, "running": 1,
                                             "oldest_pending_seconds": 30})

    def test_queue_oldest_over_1800_is_warn(self):
        queue = json.loads(json.dumps(QUEUE_OK))
        queue["oldest_pending_seconds"] = 3600
        snap = lhc.collect(FakeRunner({lhc.AGENT_HEALTH_CMD: ok_result(queue)}))
        self.assertEqual(by_name(evaluate(snap))["lynx_agent_queue"]["status"], "warn")
        self.assertEqual(evaluate(snap)["verdict"], "warn")

    def test_queue_malformed_counts_stay_unknown(self):
        queue = {"counts": {"pending": "2", "running": None, "done": "x"},
                 "oldest_pending_seconds": "12", "stopped": False, "issues": []}
        snap = lhc.collect(FakeRunner({lhc.AGENT_HEALTH_CMD: ok_result(queue)}))
        machine = snap["machine"]["lynx"]
        for key in ("pending", "running", "oldest_pending_seconds"):
            self.assertNotIn(key, machine)
        self.assertEqual(by_name(evaluate(snap))["lynx_agent_queue"]["status"], "unknown")

    def test_queue_issues_and_stopped_recorded_as_notes(self):
        queue = json.loads(json.dumps(QUEUE_OK))
        queue["issues"] = ["queue_not_private"]
        queue["stopped"] = True
        snap = lhc.collect(FakeRunner({lhc.AGENT_HEALTH_CMD: ok_result(queue)}))
        notes = " | ".join(snap["source"]["notes"])
        self.assertIn("queue_not_private", notes)
        self.assertIn("stop marker present", notes)
        # Context only: the counts are still judged normally.
        self.assertEqual(by_name(evaluate(snap))["lynx_agent_queue"]["status"], "ok")

    def test_cellular_error_object_stays_unknown(self):
        result = lhc.RunnerResult(
            1, json.dumps({"error": "lynx-status unavailable",
                           "type": "CalledProcessError"}), "")
        snap = lhc.collect(FakeRunner({lhc.CELLULAR_CMD: result}))
        self.assertNotIn("modem_md1_state", snap["machine"]["lynx"])
        self.assertEqual(by_name(evaluate(snap))["lynx_modem"]["status"], "unknown")
        self.assertFalse(snap["source"]["commands"][1]["ok"])


class FailurePathTests(unittest.TestCase):
    def test_nonzero_exit_leaves_facts_absent(self):
        runner = FakeRunner({lhc.LINUX_STATUS_CMD:
                             lhc.RunnerResult(1, "", "lynx-status: not installed")})
        snap = lhc.collect(runner)
        self.assertEqual(snap["facts"], {})
        self.assertFalse(snap["source"]["commands"][0]["ok"])
        self.assertIn("exit", snap["source"]["commands"][0]["error"])
        checks = by_name(evaluate(snap))
        self.assertEqual(checks["battery"]["status"], "unknown")
        # The other two commands still succeeded, so the known checks judge ok:
        self.assertEqual(evaluate(snap)["verdict"], "ok")
        self.assertEqual(checks["lynx_modem"]["status"], "ok")

    def test_malformed_json_is_unknown_not_ok(self):
        runner = FakeRunner({lhc.LINUX_STATUS_CMD: ok_result(raw="this is not json")})
        snap = lhc.collect(runner)
        self.assertEqual(snap["facts"], {})
        self.assertIn("malformed", snap["source"]["commands"][0]["error"])
        self.assertEqual(by_name(evaluate(snap))["battery"]["status"], "unknown")

    def test_json_array_is_rejected(self):
        runner = FakeRunner({lhc.LINUX_STATUS_CMD: ok_result(raw="[1,2,3]")})
        snap = lhc.collect(runner)
        self.assertEqual(snap["facts"], {})
        self.assertEqual(by_name(evaluate(snap))["battery"]["status"], "unknown")

    def test_cellular_timeout_leaves_modem_unknown(self):
        runner = FakeRunner({lhc.CELLULAR_CMD: lhc.RunnerTimeout(lhc.CELLULAR_CMD)})
        snap = lhc.collect(runner)
        self.assertIn("timeout", snap["source"]["commands"][1]["error"])
        self.assertNotIn("modem_md1_state", snap["machine"]["lynx"])
        self.assertEqual(by_name(evaluate(snap))["lynx_modem"]["status"], "unknown")
        self.assertEqual(snap["source"]["commands"][0]["ok"], True)
        self.assertEqual(evaluate(snap)["verdict"], "ok")

    def test_runner_exception_does_not_escape(self):
        # Aria #103: ordinary runner failures (OSError and friends) used to
        # escape collect(); now they are recorded and the facts stay absent.
        runner = FakeRunner({lhc.CELLULAR_CMD: OSError("network is unreachable")})
        snap = lhc.collect(runner)  # must not raise
        entry = snap["source"]["commands"][1]
        self.assertFalse(entry["ok"])
        self.assertIn("runner failed: OSError", entry["error"])
        self.assertNotIn("modem_md1_state", snap["machine"]["lynx"])
        self.assertEqual(by_name(evaluate(snap))["lynx_modem"]["status"], "unknown")
        # The other two commands are unaffected:
        self.assertEqual(snap["source"]["commands"][0]["ok"], True)
        self.assertEqual(snap["source"]["commands"][2]["ok"], True)
        self.assertEqual(evaluate(snap)["verdict"], "ok")

    def test_all_commands_fail_verdict_unknown(self):
        failure = lambda: lhc.RunnerResult(1, "", "gone")  # noqa: E731
        runner = FakeRunner({cmd: failure() for cmd in DEFAULTS})
        snap = lhc.collect(runner)
        self.assertEqual(snap["facts"], {})
        self.assertEqual(snap["machine"], {"lynx": {}})
        self.assertEqual(evaluate(snap)["verdict"], "unknown")

    def test_total_budget_exhaustion_skips_every_command(self):
        runner = FakeRunner()
        snap = lhc.collect(runner, total_timeout=0)
        self.assertEqual(runner.calls, [])
        for entry in snap["source"]["commands"]:
            self.assertIn("budget exhausted", entry["error"])
        self.assertEqual(evaluate(snap)["verdict"], "unknown")

    def test_per_cmd_timeout_capped_by_remaining_budget(self):
        runner = FakeRunner({lhc.LINUX_STATUS_CMD: lhc.RunnerTimeout("x")})
        lhc.collect(runner, per_cmd_timeout=15, total_timeout=2)
        self.assertLessEqual(runner.calls[0][1], 2.0)

    def test_budget_exhaustion_skips_later_commands(self):
        # First command consumes the whole budget; the other two are
        # skipped and their facts stay absent, while command 1's facts remain.
        runner = FakeRunner(delays={lhc.LINUX_STATUS_CMD: 0.3})
        snap = lhc.collect(runner, total_timeout=0.1)
        self.assertEqual(snap["source"]["commands"][0]["ok"], True)
        self.assertIn("budget exhausted", snap["source"]["commands"][1]["error"])
        self.assertIn("budget exhausted", snap["source"]["commands"][2]["error"])
        self.assertEqual(len(runner.calls), 1)
        self.assertIn("battery", snap["facts"])
        self.assertEqual(snap["machine"], {"lynx": {}})
        # Known common checks still judge:
        self.assertEqual(by_name(evaluate(snap))["battery"]["status"], "ok")
        self.assertEqual(by_name(evaluate(snap))["lynx_modem"]["status"], "unknown")

    def test_partial_state_maps_only_present_sections(self):
        partial = {"schema": 2, "battery": HEALTHY_PHONE["battery"],
                   "issues": ["thermal_unavailable"]}
        runner = FakeRunner({lhc.LINUX_STATUS_CMD: ok_result(partial)})
        snap = lhc.collect(runner)
        self.assertIn("battery", snap["facts"])
        for name in ("thermal", "storage", "network", "services"):
            self.assertNotIn(name, snap["facts"])
        self.assertEqual(snap["source"]["issues"], ["thermal_unavailable"])
        checks = by_name(evaluate(snap))
        self.assertEqual(checks["battery"]["status"], "ok")
        self.assertEqual(checks["thermal"]["status"], "unknown")
        self.assertEqual(checks["services"]["status"], "unknown")

    def test_none_and_string_values_are_not_fabricated(self):
        bad = {
            "battery": {"capacity_percent": None, "temperature_mC": "41500",
                        "current_mA_signed": "nope",
                        "read_errors": {"capacity": 2, "temperature": None}},
            "thermal": {"max_mC": None, "cooling_states": {"c": "3"}},
            "wifi": {"carrier": "yes", "ipv4": 12},
        }
        runner = FakeRunner({lhc.LINUX_STATUS_CMD: ok_result(bad)})
        snap = lhc.collect(runner)
        facts = snap["facts"]
        # A section with nothing judgeable is absent, exactly like missing:
        # the evaluator treats absence and empty identically (unknown).
        for section in ("battery", "thermal", "network", "storage", "services"):
            self.assertNotIn(section, facts)
        self.assertEqual(by_name(evaluate(snap))["battery"]["status"], "unknown")

    def test_output_is_capped(self):
        big = json.loads(json.dumps(HEALTHY_PHONE))
        big["pad"] = "x" * 20000
        runner = FakeRunner({lhc.LINUX_STATUS_CMD: ok_result(big)})
        snap = lhc.collect(runner, max_output=12000)
        self.assertTrue(snap["source"]["commands"][0]["truncated"])
        self.assertGreater(snap["source"]["commands"][0]["stdout_bytes"], 12000)


class CliTests(unittest.TestCase):
    def _patched_main(self, runner, argv):
        original = lhc.make_ssh_runner
        lhc.make_ssh_runner = lambda ip, port: runner
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = lhc.main(argv)
        finally:
            lhc.make_ssh_runner = original
        return code, buf.getvalue()

    def test_snapshot_mode_prints_snapshot_and_exits_zero(self):
        code, out = self._patched_main(FakeRunner(), [])
        self.assertEqual(code, 0)
        snap = json.loads(out)
        self.assertEqual(snap["schema"], "portable-health/1")
        self.assertEqual(snap["collector"], "lynx_health_collect/2")
        self.assertEqual(snap["machine"]["lynx"]["modem_md1_state"], 0)

    def test_evaluate_mode_returns_verdict_exit(self):
        phone = json.loads(json.dumps(HEALTHY_PHONE))
        phone["battery"]["capacity_percent"] = 19
        runner = FakeRunner({lhc.LINUX_STATUS_CMD: ok_result(phone)})
        code, out = self._patched_main(runner, ["--evaluate"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out)["verdict"], "fail")

    def test_evaluate_mode_warn_exit(self):
        cellular = json.loads(json.dumps(CELLULAR_OK))
        cellular["evidence"]["md1_state_code"] = 1
        runner = FakeRunner({lhc.CELLULAR_CMD: ok_result(cellular)})
        code, out = self._patched_main(runner, ["--evaluate"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["verdict"], "warn")

    def test_evaluate_mode_unknown(self):
        runner = FakeRunner({cmd: lhc.RunnerResult(1, "", "gone") for cmd in DEFAULTS})
        code, out = self._patched_main(runner, ["--evaluate"])
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
