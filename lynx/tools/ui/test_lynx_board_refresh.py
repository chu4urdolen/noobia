"""Offline tests for the on-demand operator entry point (no phone contact)."""

from datetime import datetime, timedelta, timezone
import io
import json
from contextlib import redirect_stdout
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import lynx_board_refresh as refresh_mod  # noqa: E402
import lynx_status_snapshot as snap  # noqa: E402
import lynx_tool_board as board  # noqa: E402
from test_lynx_status_board import BOOT, FakeLynx, catalog_text  # noqa: E402

OTHER_BOOT = "11111111-2222-3333-4444-555555555555"


def run(temp, argv, runner):
    paths = ["--status", str(Path(temp) / "latest.json"), "--out", str(Path(temp) / "board.html")]
    with redirect_stdout(io.StringIO()) as buf:
        code = refresh_mod.main(paths + argv, runner=runner)
    return code, json.loads(buf.getvalue())


def unreachable(remote):
    return 255, b"", b"ssh: connect to host 192.168.100.107 port 2222: No route to host"


def timeout(remote):
    return 124, b"", b"local timeout"


class RefreshTest(unittest.TestCase):
    def test_live_capture_complete(self):
        with TemporaryDirectory() as temp:
            fake = FakeLynx(Path(temp))
            code, result = run(temp, [], fake)
            page = (Path(temp) / "board.html").read_text()
        self.assertEqual(code, 0, result)
        self.assertTrue(result["ok"])
        self.assertEqual(result["sources"]["captured"], list(snap.COMMANDS))
        self.assertTrue(result["catalog"]["in_sync"])
        self.assertEqual(result["freshness"]["state"], "fresh")
        self.assertEqual(result["freshness"]["boot_id"], BOOT)
        self.assertEqual(result["health"], "not provided")
        self.assertEqual(fake.seen, list(snap.COMMANDS.values()))
        self.assertIn("Lynx tool board", page)
        self.assertLess(len(json.dumps(result)), 2000)  # short result

    def test_offline_mode_never_calls_ssh(self):
        with TemporaryDirectory() as temp:
            run(temp, [], FakeLynx(Path(temp)))
            boom = mock.Mock(side_effect=AssertionError("SSH used offline"))
            code, result = run(temp, ["--offline"], boom)
        self.assertEqual(code, 0, result)
        self.assertEqual(result["mode"], "offline")
        self.assertNotIn("sources", result)
        boom.assert_not_called()

    def test_offline_without_snapshot_fails_cleanly(self):
        with TemporaryDirectory() as temp:
            code, result = run(temp, ["--offline"], unreachable)
            self.assertFalse((Path(temp) / "board.html").exists())
        self.assertEqual(code, 1)
        self.assertIn("no snapshot to render", result["problems"])

    def test_ssh_failure_keeps_previous_snapshot_and_marks_stale(self):
        with TemporaryDirectory() as temp:
            run(temp, [], FakeLynx(Path(temp)))
            latest = Path(temp) / "latest.json"
            old = json.loads(latest.read_text())
            old["captured_at"] = "2026-11-20T20:00:00Z"
            latest.write_text(json.dumps(old))
            before = latest.read_text()
            code, result = run(temp, [], unreachable)
            after = latest.read_text()
            page = (Path(temp) / "board.html").read_text()
        self.assertEqual(code, 2)
        self.assertEqual(before, after)
        self.assertIn("capture failed; showing previous snapshot", result["problems"])
        self.assertIn("snapshot stale", result["problems"])
        self.assertIn("No route to host", result["sources"]["errors"]["platform"])
        self.assertIn("stale-box", page)

    def test_ssh_timeout_on_every_source(self):
        with TemporaryDirectory() as temp:
            code, result = run(temp, [], timeout)
        self.assertEqual(code, 1)
        self.assertTrue(all("exit 124" in e for e in result["sources"]["errors"].values()))

    def test_partial_status(self):
        with TemporaryDirectory() as temp:
            fake = FakeLynx(Path(temp), {"hardware": (124, b"", b"local timeout"),
                                         "catalog": (255, b"", b"ssh: broken pipe")})
            code, result = run(temp, [], fake)
        self.assertEqual(code, 2)
        self.assertIn("partial capture", result["problems"])
        self.assertIn("catalog not checked", result["problems"])
        self.assertEqual(sorted(result["sources"]["errors"]), ["catalog", "hardware"])
        self.assertIsNone(result["catalog"]["in_sync"])

    def test_reboot_and_drift_are_problems(self):
        with TemporaryDirectory() as temp:
            latest = Path(temp) / "latest.json"
            latest.write_text(json.dumps({"boot": {"boot_id": OTHER_BOOT},
                                          "captured_at": "2026-11-21T00:00:00Z"}))
            lines = [("0" * 64 + line[64:]) if line.endswith("  lynx_gnss.json") else line
                     for line in catalog_text().decode().splitlines()]
            fake = FakeLynx(Path(temp), {"catalog": (0, ("\n".join(lines) + "\n").encode(), b"")})
            code, result = run(temp, [], fake)
        self.assertEqual(code, 2)
        self.assertIn("Lynx rebooted since previous snapshot", result["problems"])
        self.assertIn("catalog drift", result["problems"])
        self.assertEqual(result["catalog"]["not_in_sync"], ["lynx_gnss"])
        self.assertEqual(result["catalog"]["counts"], {"in_sync": 37, "hash_differs": 1})

    def test_overall_deadline_skips_remaining_commands(self):
        ticks = iter([0, 1, 2, 61, 62, 63, 64])
        calls = []

        def slow(remote):
            calls.append(remote)
            return 0, b"{}", b""
        runner = refresh_mod.with_deadline(slow, 60, clock=lambda: next(ticks))
        results = [runner(r) for r in list(snap.COMMANDS.values())[:4]]
        self.assertEqual(len(calls), 2)
        self.assertEqual(results[2][0], 124)
        self.assertIn(b"deadline", results[3][2])

    def test_board_write_is_atomic(self):
        with TemporaryDirectory() as temp:
            target = Path(temp) / "board.html"
            target.write_text("old page")
            with mock.patch.object(os, "replace", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    board.write_text_atomic(target, "new page")
            self.assertEqual(target.read_text(), "old page")
            self.assertEqual([p.name for p in Path(temp).iterdir()], ["board.html"])
            board.write_text_atomic(target, "new page")
            self.assertEqual(target.read_text(), "new page")

    def test_write_failure_reports_error_json(self):
        with TemporaryDirectory() as temp:
            run(temp, [], FakeLynx(Path(temp)))
            with mock.patch.object(board, "write_text_atomic", side_effect=OSError("read-only")):
                code, result = run(temp, ["--offline"], unreachable)
        self.assertEqual(code, 1)
        self.assertFalse(result["ok"])

    def test_health_summary_when_present(self):
        health = Path(__file__).resolve().parents[1] / "health"
        sys.path.insert(0, str(health))
        from portable_health import evaluate
        report = evaluate(json.loads((health / "examples/lynx-live-20261121.json").read_text()))
        with TemporaryDirectory() as temp:
            path = Path(temp) / "health.json"
            path.write_text(json.dumps(report))
            code, result = run(temp, ["--health", str(path)], FakeLynx(Path(temp)))
        self.assertEqual(result["health"]["verdict"], "ok")
        self.assertEqual(result["health"]["unknown_checks"], 2)


if __name__ == "__main__":
    unittest.main()
