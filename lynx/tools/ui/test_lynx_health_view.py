"""Offline tests for the optional portable-health board section.

Reports are produced from Dushich's tracked example snapshots by his own
evaluator (imported read-only); nothing under lynx/tools/health is modified.
"""

from datetime import datetime, timedelta, timezone
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

HERE = Path(__file__).resolve().parent
HEALTH = HERE.parent / "health"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HEALTH))

import lynx_health_view as hv  # noqa: E402
import lynx_tool_board as board  # noqa: E402
import lynx_tool_manifest as mm  # noqa: E402
from portable_health import evaluate  # noqa: E402  (Dushich's evaluator, read-only)
from test_lynx_snapshot_age import CAPTURED, fixture  # noqa: E402


def report(example):
    snapshot = json.loads((HEALTH / "examples" / example).read_text())
    return evaluate(snapshot)


def at(report_dict):
    return hv.parse_any_time(report_dict["captured_at"])


class NormalizeTest(unittest.TestCase):
    def test_statuses_are_preserved_exactly(self):
        warn = hv.normalize(report("lynx-warn.json"))
        self.assertEqual(warn["verdict"], "warn")
        statuses = {c["name"]: c["status"] for c in warn["checks"]}
        self.assertEqual(statuses["battery"], "warn")
        live = hv.normalize(report("lynx-live-20261121.json"))
        live_statuses = {c["name"]: c["status"] for c in live["checks"]}
        self.assertEqual(live_statuses["lynx_modem"], "unknown")
        self.assertEqual(live_statuses["lynx_agent_queue"], "unknown")

    def test_full_live_capture_has_no_unknowns(self):
        full = hv.normalize(report("lynx-live-20261121-full.json"))
        self.assertEqual(full["verdict"], "ok")
        self.assertEqual({c["status"] for c in full["checks"]}, {"ok"})
        self.assertEqual(len(full["checks"]), 7)
        self.assertNotIn("checks unknown", hv.section(full, at(full)))

    def test_fail_and_unrecognized_are_never_ok(self):
        data = report("lynx-healthy.json")
        data["checks"][0]["status"] = "fail"
        data["checks"][1]["status"] = "great"
        data["verdict"] = "perfect"
        out = hv.normalize(data)
        self.assertEqual(out["checks"][0]["status"], "fail")
        self.assertEqual(out["checks"][1]["status"], "unrecognized")
        self.assertEqual(out["verdict"], "unrecognized")

    def test_missing_values_are_not_invented(self):
        data = report("lynx-healthy.json")
        data["checks"].append({"name": "mystery", "status": "unknown"})
        data["checks"].append("not a check")
        out = hv.normalize(data)
        mystery = out["checks"][-2]
        self.assertEqual((mystery["evidence"], mystery["notes"]), ("", []))
        self.assertEqual(out["checks"][-1]["status"], "unrecognized")

    def test_rejected_reports(self):
        good = report("lynx-healthy.json")
        cases = {"schema": dict(good, schema="portable-health/2"),
                 "host": dict(good, host="nexus"),
                 "no checks": {k: v for k, v in good.items() if k != "checks"},
                 "not object": ["x"]}
        for label, data in cases.items():
            with self.subTest(label), self.assertRaises(hv.HealthError):
                hv.normalize(data)

    def test_bounded_output(self):
        data = report("lynx-healthy.json")
        data["checks"] = [{"name": f"c{i}", "status": "ok", "evidence": {"x": "y" * 500},
                           "notes": ["n" * 500] * 9} for i in range(80)]
        out = hv.normalize(data)
        self.assertEqual(len(out["checks"]), hv.MAX_CHECKS)
        self.assertEqual(out["checks_truncated"], 30)
        self.assertLessEqual(len(out["checks"][0]["evidence"]), hv.EVIDENCE_CHARS + 1)
        self.assertEqual(len(out["checks"][0]["notes"]), 5)


class SectionTest(unittest.TestCase):
    def test_fresh_report_section(self):
        data = hv.normalize(report("lynx-live-20261121.json"))
        html = hv.section(data, at(data) + timedelta(minutes=1))
        self.assertIn('data-health-freshness="fresh"', html)
        self.assertIn("not validated Lynx limits", html)
        self.assertIn('class="badge h-unknown"', html)
        self.assertNotIn("These health results describe capture time", html)
        self.assertIn("2 of 7 checks unknown or unrecognized", html)

    def test_stale_offset_and_unknown_time(self):
        data = hv.normalize(report("lynx-warn.json"))  # captured_at uses +03:00
        self.assertIsNotNone(at(data))
        html = hv.section(data, at(data) + timedelta(hours=2))
        self.assertIn('data-health-freshness="stale"', html)
        self.assertIn("describe capture time, not now", html)
        data["captured_at"] = "sometime"
        self.assertIn('data-health-freshness="unknown_time"', hv.section(data, CAPTURED))

    def test_escapes_hostile_text(self):
        data = report("lynx-healthy.json")
        data["checks"][0]["notes"] = ["<script>alert(1)</script>"]
        data["checks"][0]["name"] = "<img src=x onerror=alert(1)>"
        html = hv.section(hv.normalize(data), CAPTURED)
        self.assertNotIn("<script", html)
        self.assertNotIn("<img", html)

    def test_error_is_explained(self):
        html = hv.section(None, CAPTURED, "unsupported health schema 'x'")
        self.assertIn("Health report not shown", html)


class BoardIntegrationTest(unittest.TestCase):
    def test_board_shows_health_separately_and_stays_static(self):
        health = hv.normalize(report("lynx-warn.json"))
        manifest = mm.apply_snapshot(mm.build(), fixture())
        html = board.render(manifest, CAPTURED + timedelta(minutes=1), health=health)
        self.assertIn('<a href="#health">Health</a>', html)
        self.assertIn('<h2 id="health">', html)
        self.assertIn("battery: proven", html)  # phone validation unchanged by warn
        for tag in ("<script", "<form", "<button", "<input", "http://", "https://"):
            self.assertNotIn(tag, html.lower())

    def test_board_command_with_bad_health_file_still_renders(self):
        with TemporaryDirectory() as temp:
            snap = Path(temp) / "snap.json"
            snap.write_text(json.dumps(fixture()))
            bad = Path(temp) / "health.json"
            bad.write_text(json.dumps({"schema": "other"}))
            out = Path(temp) / "board.html"
            with redirect_stdout(io.StringIO()) as buf:
                code = board.main(["--status", str(snap), "--out", str(out),
                                   "--health", str(bad)])
            result = json.loads(buf.getvalue())
            page = out.read_text()
        self.assertEqual(code, 0)
        self.assertIn("not shown: unsupported health schema", result["health"])
        self.assertIn("Health report not shown", page)

    def test_board_without_health_has_no_section(self):
        manifest = mm.apply_snapshot(mm.build(), fixture())
        html = board.render(manifest, CAPTURED)
        self.assertNotIn('id="health"', html)


if __name__ == "__main__":
    unittest.main()
