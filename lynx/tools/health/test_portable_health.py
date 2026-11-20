#!/usr/bin/env python3
"""Offline fixture tests for portable_health.py.

Nothing here contacts Lynx, Nexus, or any network. Every case feeds a
snapshot fixture into the pure evaluate() engine (or main() via a temp
file) and asserts the verdict, per-check status, evidence, and exit codes.
Run:  python3 -m unittest discover -s lynx/tools/health -p 'test_*.py'
"""

import io
import sys
import json
import os
import tempfile
import unittest

import portable_health as ph

SCHEMA = "portable-health/1"


def make_snapshot(facts=None, machine=None, host="lynx", profile=None,
                  captured_at="2026-11-21T10:00:00+03:00", schema=SCHEMA):
    snapshot = {"schema": schema, "host": host,
                "captured_at": captured_at, "facts": facts or {}}
    if profile is not None:
        snapshot["profile"] = profile
    if machine is not None:
        snapshot["machine"] = machine
    return snapshot


def check_by_name(report, name):
    for check in report["checks"]:
        if check["name"] == name:
            return check
    raise AssertionError(f"check {name!r} not present in report")


class TestBattery(unittest.TestCase):
    def test_ok(self):
        report = ph.evaluate(make_snapshot(facts={"battery": {"capacity_percent": 69}}))
        self.assertEqual(check_by_name(report, "battery")["status"], "ok")

    def test_warn_recheck_band(self):
        report = ph.evaluate(make_snapshot(facts={"battery": {"capacity_percent": 27, "charging": False}}))
        check = check_by_name(report, "battery")
        self.assertEqual(check["status"], "warn")
        self.assertTrue(any("20-35%" in note for note in check["notes"]))

    def test_fail_below_reserve(self):
        report = ph.evaluate(make_snapshot(facts={"battery": {"capacity_percent": 18, "charging": True}}))
        check = check_by_name(report, "battery")
        self.assertEqual(check["status"], "fail")
        self.assertTrue(any("reserve guard" in note for note in check["notes"]))

    def test_gauge_errors_degrade_ok_to_warn(self):
        report = ph.evaluate(make_snapshot(facts={"battery": {"capacity_percent": 80, "gauge_read_errors": 3}}))
        check = check_by_name(report, "battery")
        self.assertEqual(check["status"], "warn")
        self.assertEqual(check["evidence"]["gauge_read_errors"], 3)

    def test_missing_capacity_is_unknown_not_ok(self):
        report = ph.evaluate(make_snapshot(facts={"battery": {"gauge_read_errors": 0}}))
        self.assertEqual(check_by_name(report, "battery")["status"], "unknown")

    def test_no_battery_facts(self):
        report = ph.evaluate(make_snapshot(facts={}))
        self.assertEqual(check_by_name(report, "battery")["status"], "unknown")

    def test_string_numbers_rejected(self):
        report = ph.evaluate(make_snapshot(facts={"battery": {"capacity_percent": "69"}}))
        self.assertEqual(check_by_name(report, "battery")["status"], "unknown")


class TestThermal(unittest.TestCase):
    def test_ok(self):
        report = ph.evaluate(make_snapshot(facts={"thermal": {"max_c": 31.2}}))
        self.assertEqual(check_by_name(report, "thermal")["status"], "ok")

    def test_warn_band(self):
        report = ph.evaluate(make_snapshot(facts={"thermal": {"max_c": 44.0}}))
        self.assertEqual(check_by_name(report, "thermal")["status"], "warn")

    def test_fail_band(self):
        report = ph.evaluate(make_snapshot(facts={"thermal": {"max_c": 52.0}}))
        self.assertEqual(check_by_name(report, "thermal")["status"], "fail")

    def test_throttled_outranks_cool_reading(self):
        report = ph.evaluate(make_snapshot(facts={"thermal": {"max_c": 30.0, "throttled": True}}))
        check = check_by_name(report, "thermal")
        self.assertEqual(check["status"], "warn")
        self.assertTrue(any("throttling" in note for note in check["notes"]))

    def test_missing(self):
        report = ph.evaluate(make_snapshot(facts={}))
        self.assertEqual(check_by_name(report, "thermal")["status"], "unknown")


class TestStorage(unittest.TestCase):
    def test_ok_by_used(self):
        report = ph.evaluate(make_snapshot(facts={"storage": {"used_percent": 41}}))
        self.assertEqual(check_by_name(report, "storage")["status"], "ok")

    def test_warn_by_used(self):
        report = ph.evaluate(make_snapshot(facts={"storage": {"used_percent": 88}}))
        self.assertEqual(check_by_name(report, "storage")["status"], "warn")

    def test_fail_by_used(self):
        report = ph.evaluate(make_snapshot(facts={"storage": {"used_percent": 96}}))
        self.assertEqual(check_by_name(report, "storage")["status"], "fail")

    def test_free_mib_fallback(self):
        for free, expected in ((20000, "ok"), (400, "warn"), (100, "fail")):
            report = ph.evaluate(make_snapshot(facts={"storage": {"free_mib": free}}))
            self.assertEqual(check_by_name(report, "storage")["status"], expected, free)

    def test_fs_errors_fail_despite_space(self):
        report = ph.evaluate(make_snapshot(facts={"storage": {"used_percent": 10, "fs_errors": 2}}))
        check = check_by_name(report, "storage")
        self.assertEqual(check["status"], "fail")
        self.assertTrue(any("filesystem errors" in note for note in check["notes"]))

    def test_missing(self):
        report = ph.evaluate(make_snapshot(facts={}))
        self.assertEqual(check_by_name(report, "storage")["status"], "unknown")


class TestNetwork(unittest.TestCase):
    def test_wifi_ok(self):
        facts = {"network": {"link_state": "wifi", "carrier": True, "ipv4": "192.168.100.107"}}
        self.assertEqual(check_by_name(ph.evaluate(make_snapshot(facts=facts)), "network")["status"], "ok")

    def test_wifi_no_carrier_fails(self):
        facts = {"network": {"link_state": "wifi", "carrier": False}}
        self.assertEqual(check_by_name(ph.evaluate(make_snapshot(facts=facts)), "network")["status"], "fail")

    def test_wifi_carrier_without_ipv4_warns(self):
        facts = {"network": {"link_state": "wifi", "carrier": True}}
        self.assertEqual(check_by_name(ph.evaluate(make_snapshot(facts=facts)), "network")["status"], "warn")

    def test_usb_without_ipv4_warns_not_fails(self):
        facts = {"network": {"link_state": "usb"}}
        self.assertEqual(check_by_name(ph.evaluate(make_snapshot(facts=facts)), "network")["status"], "warn")

    def test_usb_with_ipv4_ok(self):
        facts = {"network": {"link_state": "usb", "ipv4": "192.168.100.107"}}
        self.assertEqual(check_by_name(ph.evaluate(make_snapshot(facts=facts)), "network")["status"], "ok")

    def test_none_fails(self):
        facts = {"network": {"link_state": "none"}}
        self.assertEqual(check_by_name(ph.evaluate(make_snapshot(facts=facts)), "network")["status"], "fail")

    def test_missing(self):
        report = ph.evaluate(make_snapshot(facts={}))
        self.assertEqual(check_by_name(report, "network")["status"], "unknown")


class TestServices(unittest.TestCase):
    def test_ok(self):
        facts = {"services": {"required": ["sshd", "lynx-noobd"],
                              "running": ["sshd", "lynx-noobd", "audio"], "failed": []}}
        self.assertEqual(check_by_name(ph.evaluate(make_snapshot(facts=facts)), "services")["status"], "ok")

    def test_missing_required_fails(self):
        facts = {"services": {"required": ["sshd", "lynx-noobd"], "running": ["sshd"], "failed": []}}
        check = check_by_name(ph.evaluate(make_snapshot(facts=facts)), "services")
        self.assertEqual(check["status"], "fail")
        self.assertEqual(check["evidence"]["missing"], ["lynx-noobd"])

    def test_failed_service_fails(self):
        facts = {"services": {"required": ["sshd"], "running": ["sshd"], "failed": ["lynx-noobd"]}}
        self.assertEqual(check_by_name(ph.evaluate(make_snapshot(facts=facts)), "services")["status"], "fail")

    def test_no_required_list_is_unknown(self):
        facts = {"services": {"running": ["sshd"]}}
        self.assertEqual(check_by_name(ph.evaluate(make_snapshot(facts=facts)), "services")["status"], "unknown")


class TestLynxMachineChecks(unittest.TestCase):
    def test_modem_idle_ok(self):
        report = ph.evaluate(make_snapshot(machine={"lynx": {"modem_md1_state": 0}}))
        check = check_by_name(report, "lynx_modem")
        self.assertEqual(check["status"], "ok")
        self.assertTrue(any("no-SIM" in note for note in check["notes"]))

    def test_modem_nonzero_warns(self):
        report = ph.evaluate(make_snapshot(machine={"lynx": {"modem_md1_state": 3}}))
        self.assertEqual(check_by_name(report, "lynx_modem")["status"], "warn")

    def test_modem_missing_unknown(self):
        report = ph.evaluate(make_snapshot(machine={}))
        self.assertEqual(check_by_name(report, "lynx_modem")["status"], "unknown")

    def test_agent_queue_ok(self):
        report = ph.evaluate(make_snapshot(machine={"lynx": {"pending": 1, "running": 0}}))
        self.assertEqual(check_by_name(report, "lynx_agent_queue")["status"], "ok")

    def test_agent_queue_stale_pending_warns(self):
        report = ph.evaluate(make_snapshot(machine={"lynx": {"pending": 1, "oldest_pending_seconds": 2400}}))
        self.assertEqual(check_by_name(report, "lynx_agent_queue")["status"], "warn")

    def test_machine_section_separate_from_common(self):
        report = ph.evaluate(make_snapshot(facts={"battery": {"capacity_percent": 90}}))
        scopes = {c["name"]: c["scope"] for c in report["checks"]}
        self.assertEqual(scopes["battery"], "common")
        self.assertEqual(scopes["lynx_modem"], "machine")


class TestNexusProfile(unittest.TestCase):
    def test_gpu_ecc_fail(self):
        report = ph.evaluate(make_snapshot(host="nexus", machine={"nexus": {"ecc_uncorrectable": 2}}))
        self.assertEqual(check_by_name(report, "nexus_gpu")["status"], "fail")

    def test_gpu_xid_warn(self):
        report = ph.evaluate(make_snapshot(host="nexus", machine={"nexus": {"temp_c": 50, "xid_count": 1}}))
        self.assertEqual(check_by_name(report, "nexus_gpu")["status"], "warn")

    def test_ram_bands(self):
        for pct, expected in ((90, "ok"), (5, "warn"), (1, "fail")):
            report = ph.evaluate(make_snapshot(host="nexus", machine={"nexus": {"available_pct": pct}}))
            self.assertEqual(check_by_name(report, "nexus_ram")["status"], expected, pct)

    def test_smart_failed_devices(self):
        report = ph.evaluate(make_snapshot(host="nexus", machine={"nexus": {"failed_devices": ["sda"]}}))
        self.assertEqual(check_by_name(report, "nexus_smart")["status"], "fail")

    def test_nexus_profile_has_no_battery_check(self):
        report = ph.evaluate(make_snapshot(host="nexus"))
        names = [c["name"] for c in report["checks"]]
        self.assertNotIn("battery", names)
        self.assertIn("nexus_gpu", names)

    def test_unknown_profile_reports_unknown_and_still_evaluates_common(self):
        report = ph.evaluate(make_snapshot(host="mystery", facts={"thermal": {"max_c": 30}}))
        profile = check_by_name(report, "profile")
        self.assertEqual(profile["status"], "unknown")
        self.assertEqual(check_by_name(report, "thermal")["status"], "ok")


class TestVerdict(unittest.TestCase):
    def test_fail_beats_warn(self):
        facts = {"battery": {"capacity_percent": 60}, "thermal": {"max_c": 45}, "network": {"link_state": "none"}}
        report = ph.evaluate(make_snapshot(facts=facts))
        self.assertEqual(report["verdict"], "fail")

    def test_warn_beats_ok(self):
        facts = {"battery": {"capacity_percent": 30}, "thermal": {"max_c": 30}}
        report = ph.evaluate(make_snapshot(facts=facts))
        self.assertEqual(report["verdict"], "warn")

    def test_all_ok(self):
        facts = {"battery": {"capacity_percent": 90}, "thermal": {"max_c": 25},
                 "storage": {"used_percent": 20}, "network": {"link_state": "wifi", "carrier": True, "ipv4": "10.0.0.2"},
                 "services": {"required": ["sshd"], "running": ["sshd"], "failed": []}}
        machine = {"lynx": {"modem_md1_state": 0, "pending": 0, "running": 0}}
        report = ph.evaluate(make_snapshot(facts=facts, machine=machine))
        self.assertEqual(report["verdict"], "ok")

    def test_all_unknown_verdict(self):
        report = ph.evaluate(make_snapshot(facts={}, machine={}))
        self.assertEqual(report["verdict"], "unknown")

    def test_unknown_checks_do_not_drag_verdict(self):
        facts = {"battery": {"capacity_percent": 90}}
        report = ph.evaluate(make_snapshot(facts=facts))
        self.assertEqual(report["verdict"], "ok")
        unknowns = [c["name"] for c in report["checks"] if c["status"] == "unknown"]
        self.assertIn("thermal", unknowns)


class TestStaleness(unittest.TestCase):
    def test_stale_flagged_when_older_than_max_age(self):
        from datetime import datetime, timezone
        snapshot = make_snapshot(captured_at="2026-11-21T00:00:00+00:00")
        now = datetime(2026, 11, 21, 10, 0, tzinfo=timezone.utc)
        report = ph.evaluate(snapshot, max_age_seconds=3600, now=now)
        self.assertTrue(report["stale"])

    def test_fresh_not_stale(self):
        from datetime import datetime, timezone
        snapshot = make_snapshot(captured_at="2026-11-21T09:30:00+00:00")
        now = datetime(2026, 11, 21, 10, 0, tzinfo=timezone.utc)
        report = ph.evaluate(snapshot, max_age_seconds=3600, now=now)
        self.assertFalse(report["stale"])

    def test_no_max_age_means_never_stale(self):
        report = ph.evaluate(make_snapshot(captured_at="2020-01-01T00:00:00+00:00"))
        self.assertFalse(report["stale"])

    def test_unparseable_timestamp_ignored(self):
        report = ph.evaluate(make_snapshot(captured_at="yesterday-ish"), max_age_seconds=1)
        self.assertFalse(report["stale"])


class TestSchemaAndErrors(unittest.TestCase):
    def test_wrong_schema_rejected(self):
        with self.assertRaises(ValueError):
            ph.evaluate(make_snapshot(schema="portable-health/2"))

    def test_non_dict_snapshot_rejected(self):
        with self.assertRaises(ValueError):
            ph.evaluate(["not", "a", "snapshot"])

    def test_bad_facts_type_rejected(self):
        with self.assertRaises(ValueError):
            ph.evaluate({"schema": SCHEMA, "host": "lynx", "facts": [1, 2]})

    def test_bad_machine_type_rejected(self):
        with self.assertRaises(ValueError):
            ph.evaluate({"schema": SCHEMA, "host": "lynx", "machine": "lynx"})


class TestCLI(unittest.TestCase):
    def _run_main(self, argv, stdin=None):
        old_stdin, old_stdout = sys.stdin, sys.stdout
        buf = io.StringIO()
        try:
            if stdin is not None:
                sys.stdin = io.StringIO(stdin)
            sys.stdout = buf
            code = ph.main(argv)
        finally:
            sys.stdin, sys.stdout = old_stdin, old_stdout
        return code, buf.getvalue()

    def test_exit_ok(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(make_snapshot(facts={"battery": {"capacity_percent": 90}}), handle)
            path = handle.name
        try:
            code, out = self._run_main(["--snapshot", path])
            self.assertEqual(code, 0)
            report = json.loads(out)
            self.assertEqual(report["verdict"], "ok")
        finally:
            os.unlink(path)

    def test_exit_fail(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(make_snapshot(facts={"battery": {"capacity_percent": 10}}), handle)
            path = handle.name
        try:
            code, _ = self._run_main(["--snapshot", path])
            self.assertEqual(code, 2)
        finally:
            os.unlink(path)

    def test_exit_warn(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(make_snapshot(facts={"thermal": {"max_c": 45}}), handle)
            path = handle.name
        try:
            code, _ = self._run_main(["--snapshot", path])
            self.assertEqual(code, 1)
        finally:
            os.unlink(path)

    def test_exit_unknown(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(make_snapshot(facts={}), handle)
            path = handle.name
        try:
            code, _ = self._run_main(["--snapshot", path])
            self.assertEqual(code, 3)
        finally:
            os.unlink(path)

    def test_stdin_and_bad_schema_exit_4(self):
        code, _ = self._run_main(["--snapshot", "-"], stdin=json.dumps(make_snapshot(schema="nope")))
        self.assertEqual(code, 4)

    def test_missing_file_exit_4(self):
        code, _ = self._run_main(["--snapshot", "/nonexistent/path/snapshot.json"])
        self.assertEqual(code, 4)

    def test_text_board_bounded(self):
        snapshot = make_snapshot(
            facts={"battery": {"capacity_percent": 22, "current_ma": -151, "charging": False},
                   "services": {"required": ["sshd", "lynx-noobd"],
                                "running": ["sshd", "lynx-noobd", "audio", "sensorhub", "console"],
                                "failed": []}})
        code, out = self._run_main(["--snapshot", "-", "--text"], stdin=json.dumps(snapshot))
        self.assertEqual(code, 1)
        lines = out.splitlines()
        self.assertEqual(lines[0].split("verdict:")[1].split()[0], "warn")
        for line in lines:
            self.assertLessEqual(len(line), 140, line)

    def test_json_report_is_stable_roundtrip(self):
        snapshot = make_snapshot(facts={"battery": {"capacity_percent": 90}})
        code, out = self._run_main(["--snapshot", "-"], stdin=json.dumps(snapshot))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(json.dumps(json.loads(out))), json.loads(out))


if __name__ == "__main__":
    unittest.main(verbosity=2)
