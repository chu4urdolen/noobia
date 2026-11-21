#!/usr/bin/env python3
"""Offline tests for portable_health_diff.py (D10)."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from portable_health_diff import (  # noqa: E402
    MAX_CHECKS,
    ReportError,
    diff_reports,
    format_text,
    load_report,
    main,
)
import portable_health  # noqa: E402


def make_report(checks, verdict=None):
    statuses = [st for _, _, st in checks]
    known = [st for st in statuses if st in ("ok", "warn", "fail")]
    if verdict is None:
        verdict = "unknown" if not known else max(
            known, key={"ok": 0, "warn": 1, "fail": 2}.get)
    return {
        "schema": "portable-health/1",
        "host": "lynx",
        "captured_at": "2026-11-21T00:00:00Z",
        "stale": False,
        "verdict": verdict,
        "checks": [
            {"name": n, "scope": s, "status": st, "evidence": {}, "notes": []}
            for n, s, st in checks
        ],
    }


def write(tmp: Path, name: str, data) -> Path:
    p = tmp / name
    p.write_text(data if isinstance(data, str) else json.dumps(data))
    return p


class TestDiffReports(unittest.TestCase):
    def test_identical_reports_no_changes(self):
        rep = make_report([("battery", "common", "ok"),
                           ("thermal", "common", "ok"),
                           ("lynx_modem", "machine", "unknown")])
        d = diff_reports(rep, rep)
        self.assertFalse(d["changed"])
        self.assertEqual(d["status_changes"], [])
        self.assertEqual(d["new_unknowns"], [])
        self.assertEqual(d["resolved_unknowns"], [])
        self.assertEqual(d["unchanged"], 3)
        self.assertFalse(d["verdict"]["changed"])

    def test_status_change_detected(self):
        before = make_report([("battery", "common", "ok"), ("network", "common", "ok")])
        after = make_report([("battery", "common", "warn"), ("network", "common", "ok")])
        d = diff_reports(before, after)
        self.assertTrue(d["changed"])
        self.assertEqual(d["status_changes"], [
            {"name": "battery", "scope": "common", "before": "ok", "after": "warn"}])
        self.assertEqual(d["unchanged"], 1)
        self.assertTrue(d["verdict"]["changed"])

    def test_new_unknown(self):
        before = make_report([("battery", "common", "ok"), ("lynx_modem", "machine", "ok")])
        after = make_report([("battery", "common", "ok"), ("lynx_modem", "machine", "unknown")])
        d = diff_reports(before, after)
        self.assertEqual(d["new_unknowns"], ["lynx_modem"])
        self.assertEqual(d["resolved_unknowns"], [])
        self.assertEqual(d["status_changes"][0]["after"], "unknown")

    def test_resolved_unknown(self):
        before = make_report([("battery", "common", "ok"), ("lynx_modem", "machine", "unknown")])
        after = make_report([("battery", "common", "ok"), ("lynx_modem", "machine", "ok")])
        d = diff_reports(before, after)
        self.assertEqual(d["resolved_unknowns"], ["lynx_modem"])
        self.assertEqual(d["new_unknowns"], [])

    def test_added_and_removed_checks(self):
        before = make_report([("battery", "common", "ok"),
                              ("lynx_agent_queue", "machine", "ok")])
        after = make_report([("battery", "common", "ok"),
                             ("lynx_modem", "machine", "ok")])
        d = diff_reports(before, after)
        by_name = {c["name"]: c for c in d["status_changes"]}
        self.assertIsNone(by_name["lynx_agent_queue"]["after"])
        self.assertIsNone(by_name["lynx_modem"]["before"])
        self.assertEqual(d["unchanged"], 1)

    def test_wrong_schema_rejected(self):
        with self.assertRaises(ReportError):
            diff_reports(make_report([("battery", "common", "ok")]),
                         {"schema": "other/1", "checks": [], "verdict": "ok"})

    def test_missing_checks_rejected(self):
        with self.assertRaises(ReportError):
            diff_reports(make_report([("battery", "common", "ok")]),
                         {"schema": "portable-health/1", "verdict": "ok"})

    def test_unknown_status_rejected(self):
        with self.assertRaises(ReportError):
            diff_reports(make_report([("battery", "common", "ok")]),
                         make_report([("battery", "common", "meh")], verdict="ok"))

    def test_check_count_bound_enforced(self):
        many = [(f"c{i}", "common", "ok") for i in range(MAX_CHECKS + 1)]
        with self.assertRaises(ReportError):
            diff_reports(make_report([("battery", "common", "ok")]), make_report(many))

    def test_text_format_lists_changes(self):
        before = make_report([("battery", "common", "ok"), ("lynx_modem", "machine", "unknown")])
        after = make_report([("battery", "common", "fail"), ("lynx_modem", "machine", "ok")])
        text = format_text(diff_reports(before, after))
        self.assertIn("battery: ok -> fail", text)
        self.assertIn("resolved-unknowns 1", text)
        self.assertIn("new-unknowns 0", text)


class TestLoadAndCli(unittest.TestCase):
    def _saved_reports(self, tmp: Path):
        # Two real saved snapshots -> evaluator reports (offline).
        base = HERE / "examples"
        early = portable_health.evaluate(json.loads(
            (base / "lynx-live-20261121.json").read_text()))
        late = portable_health.evaluate(json.loads(
            (base / "lynx-live-20261121-full.json").read_text()))
        b = write(tmp, "early.json", early)
        a = write(tmp, "late.json", late)
        return b, a

    def test_cli_diff_of_saved_live_reports(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            b, a = self._saved_reports(tmp)
            res = subprocess.run(
                [sys.executable, str(HERE / "portable_health_diff.py"), str(b), str(a)],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(res.returncode, 0, res.stderr)
            # The interim capture had 2 unknowns; the full capture resolved both.
            self.assertIn("resolved-unknowns 2", res.stdout)
            self.assertIn("new-unknowns 0", res.stdout)
            self.assertIn("ok -> ok", res.stdout)

    def test_cli_json_output(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            b, a = self._saved_reports(tmp)
            res = subprocess.run(
                [sys.executable, str(HERE / "portable_health_diff.py"),
                 str(b), str(a), "--json"],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(res.returncode, 0, res.stderr)
            d = json.loads(res.stdout)
            self.assertIn(d["schema"], "portable-health/1")
            self.assertIsInstance(d["resolved_unknowns"], list)

    def test_cli_invalid_json_exit4(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            b, a = self._saved_reports(tmp)
            bad = write(tmp, "bad.json", "{not json")
            res = subprocess.run(
                [sys.executable, str(HERE / "portable_health_diff.py"), str(b), str(bad)],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(res.returncode, 4)
            self.assertIn("invalid JSON", res.stderr)

    def test_cli_wrong_schema_exit4(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            b, a = self._saved_reports(tmp)
            other = write(tmp, "other.json", {"schema": "nope", "checks": [], "verdict": "ok"})
            res = subprocess.run(
                [sys.executable, str(HERE / "portable_health_diff.py"), str(b), str(other)],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(res.returncode, 4)
            self.assertIn("unsupported schema", res.stderr)

    def test_cli_oversized_report_exit4(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            b, a = self._saved_reports(tmp)
            res = subprocess.run(
                [sys.executable, str(HERE / "portable_health_diff.py"),
                 str(b), str(a), "--max-bytes", "16"],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(res.returncode, 4)
            self.assertIn("exceed bound", res.stderr)

    def test_cli_missing_file_usage_exit2(self):
        res = subprocess.run(
            [sys.executable, str(HERE / "portable_health_diff.py"),
             "/no/such/before.json", "/no/such/after.json"],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(res.returncode, 2)

    def test_load_report_function_caps(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            big = write(tmp, "big.json", "x" * 4096)
            with self.assertRaises(ReportError):
                load_report(big, max_bytes=1024)


if __name__ == "__main__":
    unittest.main()
