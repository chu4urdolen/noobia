"""Exercise runtime guard state transitions without touching host netfilter."""
import os
import pathlib
import subprocess
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE / "lynx_firewall_legacy.sh"
FAKE = '''#!/usr/bin/env python3
import json, os, pathlib, sys
path = pathlib.Path(sys.argv[0] + '.json')
state = json.loads(path.read_text()) if path.exists() else {'chain': False, 'jump': False, 'rules': []}
args = sys.argv[1:]
if args[:2] == ['-w', '2']: args = args[2:]
action = args[0] if args else ''
if action == '-N': state['chain'] = True
elif action == '-A':
    if not state['chain']: sys.exit(1)
    state['rules'].append(args[2:])
elif action == '-I':
    if os.environ.get('FAKE_FAIL_IPV6') and 'ip6' in sys.argv[0]: sys.exit(1)
    state['jump'] = True
elif action == '-C':
    if not state['jump']: sys.exit(1)
elif action == '-D': state['jump'] = False
elif action == '-F':
    if not state['chain']: sys.exit(1)
    state['rules'] = []
elif action == '-X':
    if not state['chain']: sys.exit(1)
    state['chain'] = False
elif action == '-nL':
    if not state['chain']: sys.exit(1)
else: sys.exit(2)
path.write_text(json.dumps(state))
'''


class LegacyFirewallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = pathlib.Path(self.tmp.name)
        self.v4 = root / "iptables-legacy"
        self.v6 = root / "ip6tables-legacy"
        for path in (self.v4, self.v6):
            path.write_text(FAKE)
            path.chmod(0o755)
        self.env = dict(os.environ, LYNX_IPTABLES=str(self.v4),
                        LYNX_IP6TABLES=str(self.v6),
                        LYNX_FIREWALL_STATE=str(root / "state"),
                        LYNX_FIREWALL_DELAY="1")

    def call(self, action):
        return subprocess.run(["/bin/sh", str(SCRIPT), action], env=self.env,
                              text=True, capture_output=True, timeout=8)

    def test_timer_rolls_back_both_families(self):
        self.assertEqual(self.call("enable").returncode, 0)
        self.assertEqual(self.call("status").stdout.strip(), "pending")
        import time
        time.sleep(1.8)
        self.assertEqual(self.call("status").stdout.strip(), "off")

    def test_confirm_and_disable(self):
        self.assertEqual(self.call("enable").returncode, 0)
        self.assertEqual(self.call("confirm").returncode, 0)
        self.assertEqual(self.call("status").stdout.strip(), "active")
        self.assertEqual(self.call("disable").returncode, 0)
        self.assertEqual(self.call("status").stdout.strip(), "off")

    def test_partial_insert_failure_removes_both(self):
        self.env["FAKE_FAIL_IPV6"] = "1"
        self.assertNotEqual(self.call("enable").returncode, 0)
        self.assertEqual(self.call("status").stdout.strip(), "off")


if __name__ == "__main__":
    unittest.main()
