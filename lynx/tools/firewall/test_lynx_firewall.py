"""Exercise the local rollback and confirmation path without touching a firewall."""

import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest


HERE = Path(__file__).resolve().parent


class FirewallTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.loaded = root / "loaded"
        self.nft = root / "nft"
        self.nft.write_text(
            "#!/bin/sh\n"
            'case "$1" in\n'
            '  list) test -f "$FAKE_LOADED" ;;\n'
            '  delete) rm -f "$FAKE_LOADED" ;;\n'
            '  -f) touch "$FAKE_LOADED" ;;\n'
            '  *) exit 3 ;;\n'
            'esac\n'
        )
        self.nft.chmod(0o755)
        self.env = dict(os.environ,
                        LYNX_FIREWALL_NFT=str(self.nft),
                        LYNX_FIREWALL_RULES=str(HERE / "lynx_guard.nft"),
                        LYNX_FIREWALL_STATE=str(root / "state"),
                        LYNX_FIREWALL_DELAY="1", FAKE_LOADED=str(self.loaded))

    def run_firewall(self, action):
        return subprocess.run(["/bin/sh", str(HERE / "lynx_firewall.sh"), action],
                              env=self.env, text=True, capture_output=True, timeout=5)

    def test_unconfirmed_rules_revert(self):
        self.assertEqual(self.run_firewall("enable").returncode, 0)
        self.assertTrue(self.loaded.exists())
        time.sleep(1.3)
        self.assertFalse(self.loaded.exists())
        self.assertEqual(self.run_firewall("status").stdout.strip(), "off")

    def test_confirm_and_disable(self):
        self.assertEqual(self.run_firewall("enable").returncode, 0)
        self.assertEqual(self.run_firewall("confirm").returncode, 0)
        time.sleep(1.3)
        self.assertTrue(self.loaded.exists())
        self.assertEqual(self.run_firewall("status").stdout.strip(), "active")
        self.assertEqual(self.run_firewall("disable").returncode, 0)
        self.assertFalse(self.loaded.exists())

    def test_refuse_existing_table(self):
        self.loaded.touch()
        result = self.run_firewall("enable")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already loaded", result.stderr)

    def test_old_timer_does_not_remove_new_attempt(self):
        self.env["LYNX_FIREWALL_DELAY"] = "2"
        self.assertEqual(self.run_firewall("enable").returncode, 0)
        time.sleep(0.5)
        self.assertEqual(self.run_firewall("disable").returncode, 0)
        self.assertEqual(self.run_firewall("enable").returncode, 0)
        time.sleep(1.7)  # first timer fired; second still has time left
        self.assertTrue(self.loaded.exists())
        self.assertEqual(self.run_firewall("status").stdout.strip(), "pending")
        self.assertEqual(self.run_firewall("disable").returncode, 0)


if __name__ == "__main__":
    unittest.main()
