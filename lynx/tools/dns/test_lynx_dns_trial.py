"""Check the bounded local DoT proof without changing a resolver."""
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "lynx_dns_trial.sh"


class DnsTrialTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.config = root / "dot.conf"
        self.config.write_text("test config\n")
        self.unbound = root / "fake-unbound"
        self.unbound.write_text("#!/usr/bin/env python3\nimport time\ntime.sleep(30)\n")
        self.unbound.chmod(0o755)
        for name in ("unbound-checkconf", "nslookup"):
            path = root / name
            path.write_text("#!/bin/sh\nexit 0\n")
            path.chmod(0o755)
        self.env = dict(os.environ, PATH=str(root) + ":" + os.environ["PATH"],
                        LYNX_DNS_STATE=str(root / "state"),
                        LYNX_DNS_CONFIG=str(self.config),
                        LYNX_DNS_UNBOUND=str(self.unbound),
                        LYNX_DNS_CHECKCONF=str(root / "unbound-checkconf"),
                        LYNX_DNS_DELAY="1")

    def call(self, action):
        return subprocess.run(["/bin/sh", str(SCRIPT), action], env=self.env,
                              capture_output=True, text=True, timeout=8)

    def test_timer_stops_trial(self):
        self.assertEqual(self.call("enable").returncode, 0)
        self.assertEqual(self.call("status").stdout.strip(), "pending")
        time.sleep(1.8)
        self.assertEqual(self.call("status").stdout.strip(), "off")

    def test_manual_disable(self):
        self.assertEqual(self.call("enable").returncode, 0)
        self.assertEqual(self.call("disable").returncode, 0)
        self.assertEqual(self.call("status").stdout.strip(), "off")


if __name__ == "__main__":
    unittest.main()
