"""Exercise the real Lynx safety probe function with isolated service stubs."""

from pathlib import Path
import os
import subprocess
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parent.parent / "linux-port/lynx-maintenance-watch.sh"


class SafetyProbeTest(unittest.TestCase):
    def run_probe(self, health_status: int, reserve_status: int,
                  health_detail="LYNX_HEALTH_REFUSED_stale_sample", recent_ok=False):
        source = SOURCE.read_text()
        body = source.split("recent_health_ok() {\n", 1)[1].split("\nwifi_address() {", 1)[0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "health-supervisor"
            state.mkdir()
            if recent_ok:
                (state / "pid").write_text(str(os.getpid()))
                (state / "events.log").write_text("LYNX_HEALTH_OK battery_millidegrees=25000\n")
            service = root / "rc-service"
            service.write_text("#!/bin/sh\ncase \"$1\" in lynx-health) exit \"$HEALTH_STATUS\";; lynx-battery-reserve) exit \"$RESERVE_STATUS\";; esac\nexit 2\n")
            service.chmod(0o755)
            health = root / "lynx-health-supervisor.sh"
            health.write_text(f"echo '{health_detail}' >&2; exit 1\n")
            reserve = root / "lynx-battery-reserve.sh"
            reserve.write_text("echo LYNX_BATTERY_RESERVE_capacity_56; exit 0\n")
            body = body.replace("/sbin/rc-service", str(service))
            body = body.replace("/usr/libexec/lynx-health-supervisor.sh", str(health))
            body = body.replace("/usr/libexec/lynx-battery-reserve.sh", str(reserve))
            harness = ("set -eu\nBB=/bin/busybox\nRUN=" + str(root) + "\n"
                       "event() { printf '%s\\n' \"$*\"; }\n"
                       "recent_health_ok() {\n" + body + "\nsafety_ok\n")
            env = dict(os.environ, HEALTH_STATUS=str(health_status),
                       RESERVE_STATUS=str(reserve_status))
            return subprocess.run(["/bin/sh"], input=harness, text=True,
                                  capture_output=True, env=env)

    def test_healthy_services_produce_no_fault(self):
        result = self.run_probe(0, 0)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_health_failure_is_identified(self):
        result = self.run_probe(1, 0)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("SAFETY_PROBE health_status=1 reserve_status=0", result.stdout)
        self.assertIn("health_once=1 reserve_once=0", result.stdout)
        self.assertIn("LYNX_HEALTH_REFUSED_stale_sample", result.stdout)

    def test_reserve_failure_is_identified(self):
        result = self.run_probe(0, 1)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("SAFETY_PROBE health_status=0 reserve_status=1", result.stdout)

    def test_recent_cooling_transition_does_not_count_as_guard_loss(self):
        result = self.run_probe(1, 0,
                                "LYNX_HEALTH_REFUSED cooling not applied at 50756",
                                recent_ok=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SAFETY_PROBE_DEFERRED cooling_transition_mC=50756", result.stdout)

    def test_missing_health_heartbeat_is_never_deferred(self):
        result = self.run_probe(1, 0,
                                "LYNX_HEALTH_REFUSED cooling not applied at 47000")
        self.assertEqual(result.returncode, 1, result.stderr)

    def test_high_temperature_is_never_deferred(self):
        result = self.run_probe(1, 0,
                                "LYNX_HEALTH_REFUSED cooling not applied at 55000",
                                recent_ok=True)
        self.assertEqual(result.returncode, 1, result.stderr)


if __name__ == "__main__":
    unittest.main()
