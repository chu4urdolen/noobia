"""Check the bounded local DoT proof without changing a resolver.

Gwyn 2026-11-25 (Dushich #543): enable now demands evidence that THIS unbound
talks to the DoT port and never to plain port 53. The fake unbound below opens
real sockets so the check reads the real /proc of the test machine.
"""
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
import unittest

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "lynx_dns_trial.sh"

FAKE = """#!/usr/bin/env python3
import os, socket, sys, time
mode = os.environ.get("FAKE_MODE", "dot")
keep = []
if mode in ("dot", "plain"):
    keep.append(socket.create_connection(("127.0.0.1", int(os.environ["LYNX_DNS_DOT_PORT"]))))
if mode == "plain":
    u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    u.connect(("192.0.2.1", 53))      # a plaintext upstream (TEST-NET-1; nothing is sent)
    keep.append(u)
time.sleep(30)
"""


class DnsTrialTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(8)
        self.addCleanup(self.listener.close)
        self.conns = []
        threading.Thread(target=self._accept, daemon=True).start()
        self.config = root / "dot.conf"
        self.config.write_text("test config\n")
        self.unbound = root / "fake-unbound"
        self.unbound.write_text(FAKE)
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
                        LYNX_DNS_DOT_PORT=str(self.listener.getsockname()[1]),
                        LYNX_DNS_DELAY="2", FAKE_MODE="dot")
        self.addCleanup(lambda: self.call("disable"))

    def _accept(self):
        try:
            while True:
                self.conns.append(self.listener.accept()[0])
        except OSError:
            pass

    def call(self, action, **env):
        return subprocess.run(["/bin/sh", str(SCRIPT), action], env=dict(self.env, **env),
                              capture_output=True, text=True, timeout=20)

    def test_timer_stops_trial(self):
        r = self.call("enable")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("dot=1 plain=0", r.stdout)
        self.assertEqual(self.call("status").stdout.strip(), "pending")
        time.sleep(3)
        self.assertEqual(self.call("status").stdout.strip(), "off")

    def test_manual_disable(self):
        self.assertEqual(self.call("enable").returncode, 0)
        self.assertEqual(self.call("disable").returncode, 0)
        self.assertEqual(self.call("status").stdout.strip(), "off")

    def test_no_dot_connection_is_refused_and_cleaned_up(self):
        r = self.call("enable", FAKE_MODE="none")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no proof of DNS over TLS", r.stderr)
        self.assertEqual(self.call("status").stdout.strip(), "off")

    def test_plaintext_upstream_is_refused(self):
        r = self.call("enable", FAKE_MODE="plain")
        self.assertEqual(r.returncode, 1)
        self.assertIn("plain=1", r.stderr)
        self.assertEqual(self.call("status").stdout.strip(), "off")


if __name__ == "__main__":
    unittest.main()
