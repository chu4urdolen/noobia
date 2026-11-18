#!/usr/bin/env python3
"""Offline checks for the late Bluetooth trial's watchdog behavior."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from trial_v52_bluetooth_after_alpine import build_watchdog_script


class WatchdogTests(unittest.TestCase):
    def test_default_reboot_script_remains_identical(self):
        guard = "/run/lynx-bt-late-trial-123"
        expected = ("#!/bin/sh\n"
                    "sleep 300\n"
                    f"test -e {guard}/cancel && exit 0\n"
                    f"echo timeout > {guard}/state\n"
                    "exec /sbin/openrc-shutdown -r now\n")
        self.assertEqual(build_watchdog_script(300, guard), expected)
        self.assertEqual(build_watchdog_script(300, guard, "reboot"), expected)

    def test_stop_only_is_bounded_and_never_requests_reboot(self):
        script = build_watchdog_script(300, "/run/lynx-bt-late-trial-123", "stop-only")
        self.assertIn("/usr/bin/timeout 90 /sbin/rc-service lynx-bluetooth stop", script)
        self.assertNotIn("openrc-shutdown", script)
        self.assertNotIn("reboot", script)
        self.assertNotIn("poweroff", script)
        self.assertEqual(subprocess.run(["/bin/sh", "-n"], input=script,
                                        text=True, capture_output=True).returncode, 0)

    def test_stop_only_runs_once_and_records_result(self):
        for stop_exit in (0, 124):
            with self.subTest(stop_exit=stop_exit), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                guard = root / "guard"
                guard.mkdir()
                fake_bin = root / "bin"
                fake_bin.mkdir()
                (fake_bin / "sleep").write_text("#!/bin/sh\nexit 0\n")
                (fake_bin / "sleep").chmod(0o755)
                # The generated script calls an absolute timeout path. Replace
                # that path only in this local test; the production script is
                # checked separately above.
                fake_timeout = fake_bin / "timeout"
                fake_timeout.write_text(
                    "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$WATCHDOG_TEST_LOG\"\n"
                    "exit \"$WATCHDOG_TEST_EXIT\"\n")
                fake_timeout.chmod(0o755)
                script = build_watchdog_script(1, str(guard), "stop-only")
                script = script.replace("/usr/bin/timeout", str(fake_timeout))
                script_file = root / "watchdog.sh"
                script_file.write_text(script)
                log = root / "calls.log"
                env = dict(os.environ, PATH=str(fake_bin) + ":" + os.environ["PATH"],
                           WATCHDOG_TEST_LOG=str(log), WATCHDOG_TEST_EXIT=str(stop_exit))
                result = subprocess.run(["/bin/sh", str(script_file)], env=env,
                                        capture_output=True, text=True, timeout=3)
                self.assertEqual(result.returncode, stop_exit)
                self.assertEqual(log.read_text().strip(),
                                 "90 /sbin/rc-service lynx-bluetooth stop")
                self.assertEqual((guard / "state").read_text().strip(),
                                 f"stop_exit={stop_exit}")

                (guard / "cancel").touch()
                log.unlink()
                result = subprocess.run(["/bin/sh", str(script_file)], env=env,
                                        capture_output=True, text=True, timeout=3)
                self.assertEqual(result.returncode, 0)
                self.assertFalse(log.exists())

    def test_unknown_mode_rejected(self):
        with self.assertRaises(ValueError):
            build_watchdog_script(300, "/run/lynx-bt-late-trial-123", "poweroff")


if __name__ == "__main__":
    unittest.main()
