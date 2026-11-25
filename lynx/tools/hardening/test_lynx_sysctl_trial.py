"""Verify rollback and confirmation using fake procfs values."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

import lynx_sysctl_trial as trial


HERE = Path(__file__).resolve().parent


class SysctlTrialTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.proc = root / "proc"
        self.state = root / "state"
        self.before = {}
        for index, key in enumerate(trial.TARGETS):
            path = self.proc / key
            path.parent.mkdir(parents=True, exist_ok=True)
            value = str(index % 2)
            path.write_text(value + "\n")
            self.before[key] = value
        self.env = dict(os.environ, LYNX_SYSCTL_ROOT=str(self.proc),
                        LYNX_SYSCTL_STATE=str(self.state), LYNX_SYSCTL_DELAY="1")

    def run_trial(self, action):
        return subprocess.run([sys.executable, str(HERE / "lynx_sysctl_trial.py"), action],
                              env=self.env, text=True, capture_output=True, timeout=5)

    def values(self):
        return {key: (self.proc / key).read_text().strip() for key in trial.TARGETS}

    def test_unconfirmed_values_revert(self):
        self.assertEqual(self.run_trial("enable").returncode, 0)
        self.assertEqual(self.values(), trial.TARGETS)
        time.sleep(1.3)
        self.assertEqual(self.values(), self.before)
        self.assertEqual(self.run_trial("status").stdout.strip(), "off")

    def test_confirm_and_disable_restore_exact_values(self):
        self.assertEqual(self.run_trial("enable").returncode, 0)
        self.assertEqual(self.run_trial("confirm").returncode, 0)
        time.sleep(1.3)
        self.assertEqual(self.values(), trial.TARGETS)
        self.assertEqual(self.run_trial("disable").returncode, 0)
        self.assertEqual(self.values(), self.before)

    def test_second_enable_refuses_to_replace_snapshot(self):
        self.assertEqual(self.run_trial("enable").returncode, 0)
        again = self.run_trial("enable")
        self.assertNotEqual(again.returncode, 0)
        self.assertIn("already active", again.stderr)
        self.assertEqual(self.run_trial("disable").returncode, 0)

    def test_old_timer_cannot_revert_a_new_trial(self):
        self.env["LYNX_SYSCTL_DELAY"] = "2"
        self.assertEqual(self.run_trial("enable").returncode, 0)
        time.sleep(0.5)
        self.assertEqual(self.run_trial("disable").returncode, 0)
        self.assertEqual(self.run_trial("enable").returncode, 0)
        time.sleep(1.7)
        self.assertEqual(self.values(), trial.TARGETS)
        self.assertEqual(self.run_trial("status").stdout.strip(), "pending")
        self.assertEqual(self.run_trial("disable").returncode, 0)

    def test_restore_continues_after_one_key_fails_and_keeps_snapshot(self):
        self.assertEqual(self.run_trial("enable").returncode, 0)
        first_key = next(iter(trial.TARGETS))
        (self.proc / first_key).unlink()
        (self.proc / first_key).mkdir()
        result = self.run_trial("disable")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(first_key, result.stderr)
        self.assertEqual((self.proc / "kernel/dmesg_restrict").read_text().strip(),
                         self.before["kernel/dmesg_restrict"])
        self.assertTrue((self.state / "snapshot.json").exists())
        (self.proc / first_key).rmdir()
        (self.proc / first_key).write_text(trial.TARGETS[first_key] + "\n")
        self.assertEqual(self.run_trial("disable").returncode, 0)
        self.assertEqual(self.values(), self.before)


if __name__ == "__main__":
    unittest.main()
