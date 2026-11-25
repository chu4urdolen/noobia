#!/usr/bin/env python3
"""lynx-config-audit on a fake root."""
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lynx_config_audit as a  # noqa: E402


class ConfigAuditTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.put("etc/lynx/nrp-nexus.key", "k", 0o600)
        self.put("root/.ssh/authorized_keys", "ssh-ed25519 AAAA", 0o600)
        self.put("usr/local/bin/lynx-agent", "#!", 0o755)
        self.put("var/lib/noobia/lynx_thought.txt", "hello", 0o600)
        for rel in a.PINS:
            self.put(rel, "pinned " + rel, 0o755)
        for key, (good, _, _) in a.SYSCTLS.items():
            self.put("proc/sys/" + key, sorted(good)[0] + "\n", 0o644)
        self.put("proc/sys/kernel/osrelease", "5.10.149-test\n", 0o644)
        self.pins = {rel: hashlib.sha256(("pinned " + rel).encode()).hexdigest() for rel in a.PINS}

    def tearDown(self):
        self.tmp.cleanup()

    def put(self, rel, text, mode):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        os.chmod(p, mode)

    def run_audit(self):
        with mock.patch.dict(a.PINS, self.pins):
            return a.audit(self.root)

    def ids(self, r, level=None):
        return {f["id"].split(":")[0] for f in r["findings"] if level is None or f["level"] == level}

    def test_clean_lynx_is_ok(self):
        r = self.run_audit()
        self.assertTrue(r["ok"], r["findings"])
        self.assertEqual(set(r["facts"]["boot_pins"].values()), {"match"})
        self.assertEqual(self.ids(r), {"pinned-packages"})

    def test_readable_secret_and_world_writable_program_are_high(self):
        os.chmod(self.root / "etc/lynx/nrp-nexus.key", 0o644)
        os.chmod(self.root / "usr/local/bin/lynx-agent", 0o777)
        r = self.run_audit()
        self.assertFalse(r["ok"])
        self.assertTrue({"secret-world-readable", "file-world-writable"} <= self.ids(r, "high"))

    def test_wifi_credential_file_must_be_private(self):
        self.put("etc/lynx/wpa_supplicant.conf", "network={...}", 0o644)
        r = self.run_audit()
        self.assertIn("secret-world-readable", self.ids(r, "high"))

    def test_group_readable_inference_key_only_for_lynx_agent(self):
        self.put("etc/lynx/nexus-inference.key", "k", 0o640)
        with mock.patch.object(a, "_group_name", lambda gid: "lynx-agent"):
            self.assertTrue(self.run_audit()["ok"])
        with mock.patch.object(a, "_group_name", lambda gid: "users"):
            self.assertIn("secret-group-readable", self.ids(self.run_audit(), "high"))

    def test_a_changed_pinned_file_warns_of_a_refused_boot(self):
        (self.root / "etc/init.d/lynx-health").write_text("edited")
        r = self.run_audit()
        self.assertFalse(r["ok"])
        self.assertEqual(r["facts"]["boot_pins"]["etc/init.d/lynx-health"], "DIFFERENT")
        self.assertTrue(any("REFUSED" in f["text"] for f in r["findings"]))

    def test_weak_kernel_settings_and_private_logs(self):
        self.put("proc/sys/kernel/kptr_restrict", "0\n", 0o644)
        self.put("proc/sys/kernel/randomize_va_space", "0\n", 0o644)
        os.chmod(self.root / "var/lib/noobia/lynx_thought.txt", 0o644)
        r = self.run_audit()
        self.assertIn("sysctl", self.ids(r, "warn"))
        self.assertIn("sysctl", self.ids(r, "high"))
        self.assertIn("private-log-readable", self.ids(r, "warn"))
        self.assertTrue(a.text_report(r).startswith("Lynx config audit: ATTENTION"))


if __name__ == "__main__":
    unittest.main()
