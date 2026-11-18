#!/usr/bin/env python3
"""Offline checks for the Lynx remote command helper and result digester."""

import argparse
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lynx_remote


class ResultDigestTests(unittest.TestCase):
    def _write_result(self, folder, name, data):
        directory = Path(folder) / name
        directory.mkdir(parents=True)
        (directory / "result.json").write_text(json.dumps(data))

    def test_digest_reports_health_samples_and_final_steps(self):
        with tempfile.TemporaryDirectory() as folder:
            self._write_result(folder, "v53-bt-after-alpine-1", {
                "state": "pass", "boot_id": "abc", "watchdog_mode": "stop-only",
                "nexus": {"state": "ok"},
                "steps": [
                    {"name": "setup", "exit": 0},
                    {"name": "health_sample_1", "exit": 0},
                    {"name": "health_sample_2", "exit": 0},
                    {"name": "teardown", "exit": 0},
                ],
            })
            lynx_remote.LOGS = Path(folder)
            args = argparse.Namespace(glob="v53-bt-after-alpine-*", limit=1)
            self.assertEqual(lynx_remote.cmd_result(args), 0)

    def test_digest_flags_failing_sample(self):
        with tempfile.TemporaryDirectory() as folder:
            self._write_result(folder, "v53-bt-after-alpine-1", {
                "state": "fail",
                "steps": [{"name": "health_sample_1", "exit": 1}],
            })
            lynx_remote.LOGS = Path(folder)
            args = argparse.Namespace(glob="*", limit=2)
            self.assertEqual(lynx_remote.cmd_result(args), 0)

    def test_no_match_is_an_error(self):
        with tempfile.TemporaryDirectory() as folder:
            lynx_remote.LOGS = Path(folder)
            args = argparse.Namespace(glob="nothing-*", limit=1)
            self.assertEqual(lynx_remote.cmd_result(args), 1)


class RunCommandTests(unittest.TestCase):
    def test_argv_uses_pinned_key_and_injected_port(self):
        captured = {}

        def fake_run(argv, **kwargs):
            captured["argv"] = argv
            captured["timeout"] = kwargs.get("timeout")
            return subprocess.CompletedProcess(argv, 0, stdout=b"hello\n", stderr=b"")

        argv0 = lynx_remote.subprocess.run
        lynx_remote.subprocess.run = fake_run
        try:
            args = argparse.Namespace(command="echo hi", ip="192.168.100.107",
                                      port=2222, timeout=15, max_output=500)
            self.assertEqual(lynx_remote.cmd_run(args), 0)
        finally:
            lynx_remote.subprocess.run = argv0
        argv = captured["argv"]
        self.assertIn("-p", argv)
        self.assertIn("2222", argv)
        self.assertEqual(argv[argv.index("-p") + 1], "2222")
        self.assertIn("root@192.168.100.107", argv)
        self.assertIn("echo hi", argv)
        self.assertTrue(any("ed25519" in part for part in argv))
        self.assertEqual(captured["timeout"], 15)

    def test_timeout_returns_124(self):
        def boom(argv, **kwargs):
            raise subprocess.TimeoutExpired(argv, 5, output=b"partial\n")

        argv0 = lynx_remote.subprocess.run
        lynx_remote.subprocess.run = boom
        try:
            args = argparse.Namespace(command="echo hi", ip="192.168.100.107",
                                      port=2222, timeout=5, max_output=500)
            self.assertEqual(lynx_remote.cmd_run(args), 124)
        finally:
            lynx_remote.subprocess.run = argv0


if __name__ == "__main__":
    unittest.main()
