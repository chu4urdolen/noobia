"""Offline tests for noobia-quiet-trace.initd: runs start() under sh with OpenRC stubs."""

from pathlib import Path
import subprocess
import tempfile
import unittest

INITD = Path(__file__).resolve().parent / "noobia-quiet-trace.initd"
STUBS = 'ebegin(){ :; }; einfo(){ echo "INFO $*"; }; eend(){ [ "$1" = 0 ] || echo "FAIL $2"; return "$1"; }\n'


def run_start(sysctl, disable):
    body = INITD.read_text().split("\n", 1)[1]           # drop the openrc-run shebang
    script = STUBS + f'QUIET_TRACE_SYSCTL="{sysctl}"; QUIET_TRACE_DISABLE="{disable}"\n' + body + "\nstart\n"
    return subprocess.run(["sh", "-c", script], capture_output=True, text=True, timeout=10)


class QuietTraceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.sysctl = Path(self.tmp.name) / "tracepoint_printk"
        self.sysctl.write_text("1\n")
        self.disable = Path(self.tmp.name) / "quiet-trace.disable"

    def test_clears_tracepoint_printk(self):
        r = run_start(self.sysctl, self.disable)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.sysctl.read_text().strip(), "0")

    def test_disable_switch_leaves_value(self):
        self.disable.touch()
        r = run_start(self.sysctl, self.disable)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.sysctl.read_text().strip(), "1")
        self.assertIn("disabled", r.stdout)

    def test_missing_sysctl_fails_honestly(self):
        r = run_start(Path(self.tmp.name) / "absent", self.disable)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not writable", r.stdout)

    def test_runs_before_logging_and_never_restarts_it(self):
        text = INITD.read_text()
        self.assertIn("before lynx-local-logs", text)
        self.assertNotIn("need lynx-local-logs", text)   # no dependency -> no restart cascade
        self.assertNotIn("rc-service", text)


if __name__ == "__main__":
    unittest.main()
