"""Offline tests for nexus_health_collect.py (D11).

Every subprocess and filesystem touch is replaced with an injected fake, so
the suite is hermetic: it passes on a laptop with no GPU, no smartctl, and
no ollama.  The collector's honesty contract is the point under test: a
reader that fails, times out, or finds no source leaves the fact ABSENT and
the evaluator then reports ``unknown`` — never ``ok``.
"""

import io
import json
import re
import sys
import contextlib
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import nexus_health_collect as n  # noqa: E402
import portable_health as ph  # noqa: E402


MEMINFO = "MemTotal: 1000000 kB\nMemAvailable: 500000 kB\n"


class _FakeDev:
    def __init__(self, name):
        self.name = name


class _FakePath:
    """Stands in for nexus_health_collect.Path in read_smart / read_ram."""

    devs = ["nvme0"]

    def __init__(self, *parts):
        self.parts = parts

    def iterdir(self):
        return [_FakeDev(d) for d in self.devs]

    def read_text(self):
        return MEMINFO


def snap(**over):
    base = {
        "schema": "portable-health/1",
        "host": "nexus",
        "profile": "nexus",
        "captured_at": "2026-11-21T00:00:00+00:00",
        "collector": "test",
        "route": "local",
        "facts": {},
        "machine": {},
    }
    base.update(over)
    return base


def good_facts():
    return {
        "thermal": {"max_c": 40.0},
        "storage": {"used_percent": 11.4, "free_mib": 1_000_000},
        "network": {"link_state": "wifi", "carrier": True, "ipv4": "192.168.1.5"},
        "services": {"required": ["ollama"], "running": ["ollama"], "failed": []},
    }


def good_nexus_machine():
    return {"temp_c": 40, "xid_count": 0, "available_pct": 80.0,
            "checked": 1, "failed_devices": []}


class CollectAssemblyTest(unittest.TestCase):
    def test_happy_path_shape_and_machine_merge(self):
        with mock.patch.object(n, "read_ram", return_value={"available_pct": 80.0}), \
             mock.patch.object(n, "read_smart", return_value={"checked": 1, "failed_devices": []}), \
             mock.patch.object(n, "read_gpu_temp", return_value={"temp_c": 40.0}), \
             mock.patch.object(n, "read_xid_count", return_value={"xid_count": 0}), \
             mock.patch.object(n, "read_ecc_uncorrectable", return_value=None):
            out = n.collect({
                "thermal": lambda: {"max_c": 40.0},
                "storage": lambda: {"used_percent": 11.4, "free_mib": 100},
                "network": lambda: None,
                "services": lambda: {"required": ["a"], "running": ["a"], "failed": []},
            })
        self.assertEqual(out["schema"], "portable-health/1")
        self.assertEqual(out["host"], "nexus")
        self.assertEqual(out["profile"], "nexus")
        self.assertEqual(out["route"], "local")
        self.assertIn("captured_at", out)
        self.assertEqual(set(out["facts"]), {"thermal", "storage", "services"})
        self.assertEqual(out["machine"]["nexus"], good_nexus_machine())

    def test_reader_exception_leaves_fact_absent(self):
        def boom():
            raise RuntimeError("no such file")
        out = n.collect({"thermal": boom,
                        "storage": lambda: {"used_percent": 1.0},
                        "network": lambda: None,
                        "services": lambda: None})
        self.assertNotIn("thermal", out["facts"])
        self.assertIn("storage", out["facts"])

    def test_all_readers_failing_gives_unknown_verdict_and_exit_3(self):
        with mock.patch.object(n, "read_ram", return_value=None), \
             mock.patch.object(n, "read_smart", return_value=None), \
             mock.patch.object(n, "_merge_gpu", return_value=None):
            out = n.collect({"thermal": lambda: None,
                            "storage": lambda: None,
                            "network": lambda: None,
                            "services": lambda: None})
        self.assertEqual(out["facts"], {})
        self.assertEqual(out["machine"], {})
        report = ph.evaluate(out)
        self.assertEqual(report["verdict"], "unknown")
        self.assertEqual(ph.EXIT_BY_VERDICT[report["verdict"]], 3)
        for check in report["checks"]:
            self.assertEqual(check["status"], "unknown")


class ReaderHonestyTest(unittest.TestCase):
    """Failing/absent sources must yield None (absent), never a guess."""

    def test_services_all_active(self):
        with mock.patch.object(n, "_run", return_value=(0, "active active\n")):
            facts = n.read_services()
        self.assertEqual(facts["running"], ["ollama", "gpu_monitor"])
        self.assertEqual(facts["failed"], [])

    def test_services_failed_detected(self):
        with mock.patch.object(n, "_run", return_value=(0, "active failed\n")):
            facts = n.read_services()
        self.assertEqual(facts["failed"], ["gpu_monitor"])
        report = ph.evaluate(snap(facts={"services": facts}))
        services = next(c for c in report["checks"] if c["name"] == "services")
        self.assertEqual(services["status"], "fail")

    def test_services_timeout_is_absent(self):
        with mock.patch.object(n, "_run", return_value=None):
            self.assertIsNone(n.read_services())

    def test_services_empty_required_is_unknown_not_ok(self):
        facts = {"required": [], "running": [], "failed": []}
        report = ph.evaluate(snap(facts={"services": facts}))
        services = next(c for c in report["checks"] if c["name"] == "services")
        self.assertEqual(services["status"], "unknown")

    def test_ram_percent_from_meminfo(self):
        with mock.patch.object(n, "Path", _FakePath):
            self.assertEqual(n.read_ram(), {"available_pct": 50.0})

    def test_ram_missing_fields_is_absent(self):
        class NoFields(_FakePath):
            def read_text(self):
                return "Slab: 1 kB\n"
        with mock.patch.object(n, "Path", NoFields):
            self.assertIsNone(n.read_ram())

    def test_network_v1_refuses_to_mislabel_wired_uplink(self):
        self.assertIsNone(n.read_network())

    def test_gpu_and_xid_absent_when_commands_fail(self):
        with mock.patch.object(n, "_run", return_value=None):
            self.assertIsNone(n.read_gpu_temp())
            self.assertIsNone(n.read_xid_count())
            self.assertIsNone(n.read_ecc_uncorrectable())

    def test_xid_counts_matching_lines_only(self):
        out = "boot line\nNVRM: Xid 31: channel\nnoise\nNVRM: Xid 63: row\n"
        with mock.patch.object(n, "_run", return_value=(0, out)):
            self.assertEqual(n.read_xid_count(), {"xid_count": 2})

    def test_gpu_temp_parsed(self):
        with mock.patch.object(n, "_run", return_value=(0, "65\n")):
            self.assertEqual(n.read_gpu_temp(), {"temp_c": 65.0})


class SmartReaderTest(unittest.TestCase):
    def _patch_path(self):
        return mock.patch.object(n, "Path", _FakePath)

    def test_sudo_fallback_after_permission_denied(self):
        calls = []

        def fake_run(cmd, **kw):
            calls.append(cmd)
            if cmd[0] == "sudo":
                return 0, "SMART overall-health self-assessment test result: PASSED"
            return 2, "smartctl open device: /dev/nvme0 failed: Permission denied"

        with self._patch_path(), mock.patch.object(n, "_run", side_effect=fake_run):
            facts = n.read_smart()
        self.assertEqual(facts, {"checked": 1, "failed_devices": []})
        self.assertEqual(calls[0][0], n.SMARTCTL_CANDIDATES[0])
        self.assertEqual(calls[1][0], "sudo")
        self.assertIn("-n", calls[1])  # passwordless only, never a prompt

    def test_failed_device_reported(self):
        with self._patch_path(), \
             mock.patch.object(n, "_run", return_value=(0, "SMART overall-health self-assessment test result: FAILED")):
            facts = n.read_smart()
        self.assertEqual(facts["failed_devices"], ["nvme0"])
        report = ph.evaluate(snap(machine={"nexus": facts}))
        smart = next(c for c in report["checks"] if c["name"] == "nexus_smart")
        self.assertEqual(smart["status"], "fail")

    def test_smartctl_missing_is_absent(self):
        with mock.patch.object(n, "SMARTCTL_CANDIDATES", ("/no/smartctl",)):
            self.assertIsNone(n.read_smart())

    def test_no_nvme_devices_is_absent(self):
        with self._patch_path():
            _FakePath.devs = []
            try:
                self.assertIsNone(n.read_smart())
            finally:
                _FakePath.devs = ["nvme0"]

    def test_sudo_also_denied_is_absent(self):
        with self._patch_path(), \
             mock.patch.object(n, "_run", return_value=(1, "sudo: a password is required")):
            self.assertIsNone(n.read_smart())


class CliTest(unittest.TestCase):
    def _run_main(self, argv, snapshot):
        buf = io.StringIO()
        with mock.patch.object(n, "collect", return_value=snapshot), \
             contextlib.redirect_stdout(buf):
            code = n.main(argv)
        return code, buf.getvalue()

    def test_main_prints_snapshot_json(self):
        fixed = snap(facts=good_facts(), machine={"nexus": good_nexus_machine()})
        code, out = self._run_main([], fixed)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), fixed)

    def test_evaluate_exit_code_warn(self):
        fixed = snap(facts=good_facts(),
                     machine={"nexus": {**good_nexus_machine(), "xid_count": 1}})
        code, out = self._run_main(["--evaluate"], fixed)
        report = json.loads(out)
        self.assertEqual(report["verdict"], "warn")
        self.assertEqual(code, 1)

    def test_evaluate_exit_code_ok(self):
        fixed = snap(facts=good_facts(), machine={"nexus": good_nexus_machine()})
        code, out = self._run_main(["--evaluate"], fixed)
        self.assertEqual(json.loads(out)["verdict"], "ok")
        self.assertEqual(code, 0)

    def test_evaluate_text_board(self):
        fixed = snap(facts=good_facts(), machine={"nexus": good_nexus_machine()})
        code, out = self._run_main(["--evaluate", "--text"], fixed)
        self.assertIn("nexus — verdict: ok", out)

    def test_evaluate_stale_flag(self):
        fixed = snap(facts=good_facts(), machine={"nexus": good_nexus_machine()})
        code, out = self._run_main(["--evaluate", "--max-age", "1"], fixed)
        self.assertTrue(json.loads(out)["stale"])


class UnitTest(unittest.TestCase):
    def test_nvme_regex_matches_bare_name(self):
        self.assertTrue(n.NVME_RE.match("nvme0"))
        self.assertTrue(n.NVME_RE.match("nvme12"))
        self.assertFalse(n.NVME_RE.match("nvme0n1"))
        self.assertFalse(n.NVME_RE.match("/dev/nvme0"))

    def test_read_int(self):
        self.assertEqual(n._read_int("temp 65 C"), 65)
        self.assertEqual(n._read_int("-4"), -4)
        self.assertIsNone(n._read_int("nope"))
        self.assertIsNone(n._read_int(None))


if __name__ == "__main__":
    unittest.main()
