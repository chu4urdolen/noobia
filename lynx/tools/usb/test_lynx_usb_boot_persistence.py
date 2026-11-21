#!/usr/bin/env python3
"""Unit tests for lynx_usb_boot_persistence.py."""

import json
from pathlib import Path
import subprocess
import sys
import unittest

from lynx_usb_boot_persistence import (
    evaluate_boot_persistence,
    validate_init_script,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
TOOL_PATH = Path(__file__).resolve().parent / "lynx_usb_boot_persistence.py"
INIT_SCRIPT_PATH = Path(__file__).resolve().parent / "lynx-usb-gadget.initd"


class TestLynxUsbBootPersistence(unittest.TestCase):
    def test_valid_init_script_file(self):
        self.assertTrue(INIT_SCRIPT_PATH.exists())
        content = INIT_SCRIPT_PATH.read_text()
        ok, failures = validate_init_script(content)
        self.assertTrue(ok, f"Script validation failed: {failures}")
        self.assertEqual(len(failures), 0)

    def test_invalid_shebang(self):
        script = "#!/bin/sh\n"
        ok, failures = validate_init_script(script)
        self.assertFalse(ok)
        self.assertIn("missing_or_invalid_openrc_shebang", failures)

    def test_missing_depend_block(self):
        script = "#!/sbin/openrc-run\n/etc/lynx/disable-usb-gadget\n11201000.usb0\necho \"\" > \"$GADGET_DIR/UDC\"\ntimeout -t 5\n"
        ok, failures = validate_init_script(script)
        self.assertFalse(ok)
        self.assertIn("missing_depend_block", failures)

    def test_missing_after_bootmisc(self):
        script = """#!/sbin/openrc-run
depend() {
    after sshd
}
/etc/lynx/disable-usb-gadget
11201000.usb0
echo "" > "$GADGET_DIR/UDC"
timeout -t 5
"""
        ok, failures = validate_init_script(script)
        self.assertFalse(ok)
        self.assertIn("ordering_must_declare_after_bootmisc_or_modules", failures)

    def test_require_after_sshd(self):
        script = """#!/sbin/openrc-run
depend() {
    after bootmisc
}
/etc/lynx/disable-usb-gadget
11201000.usb0
echo "" > "$GADGET_DIR/UDC"
timeout -t 5
"""
        ok, failures = validate_init_script(script)
        self.assertFalse(ok)
        self.assertIn("ordering_must_declare_after_sshd", failures)

    def test_reject_before_sshd(self):
        """Rejecting 'before sshd' to ensure the USB gadget can never delay recovery."""
        script = """#!/sbin/openrc-run
depend() {
    after bootmisc modules sshd
    before sshd
}
/etc/lynx/disable-usb-gadget
11201000.usb0
echo "" > "$GADGET_DIR/UDC"
timeout -t 5
"""
        ok, failures = validate_init_script(script)
        self.assertFalse(ok)
        self.assertIn("forbidden_ordering_before_sshd", failures)

    def test_forbidden_networking_dependency(self):
        script = """#!/sbin/openrc-run
depend() {
    after bootmisc modules sshd
    need net
}
/etc/lynx/disable-usb-gadget
11201000.usb0
echo "" > "$GADGET_DIR/UDC"
timeout -t 5
"""
        ok, failures = validate_init_script(script)
        self.assertFalse(ok)
        self.assertIn("forbidden_need_dependency_on_networking", failures)

    def test_missing_disable_switch(self):
        script = """#!/sbin/openrc-run
depend() {
    after bootmisc modules sshd
}
11201000.usb0
echo "" > "$GADGET_DIR/UDC"
timeout -t 5
"""
        ok, failures = validate_init_script(script)
        self.assertFalse(ok)
        self.assertIn("missing_local_disable_switch_check", failures)

    def test_missing_bounded_timeouts(self):
        script = """#!/sbin/openrc-run
depend() {
    after bootmisc modules sshd
}
/etc/lynx/disable-usb-gadget
11201000.usb0
echo "" > "$GADGET_DIR/UDC"
"""
        ok, failures = validate_init_script(script)
        self.assertFalse(ok)
        self.assertIn("missing_bounded_timeouts_in_start", failures)

    def test_fixture_persistent_enabled(self):
        path = FIXTURES_DIR / "boot-persistence-valid-enabled.json"
        data = json.loads(path.read_text())
        verdict = evaluate_boot_persistence(data, init_script_text=INIT_SCRIPT_PATH.read_text())
        self.assertEqual(verdict.status, "PERSISTENT_ENABLED")
        self.assertTrue(verdict.is_valid)
        self.assertTrue(verdict.is_persistent)
        self.assertFalse(verdict.disable_switch_active)
        self.assertTrue(verdict.service_in_runlevel)

    def test_fixture_disabled_switch(self):
        path = FIXTURES_DIR / "boot-persistence-disabled-switch.json"
        data = json.loads(path.read_text())
        verdict = evaluate_boot_persistence(data, init_script_text=INIT_SCRIPT_PATH.read_text())
        self.assertEqual(verdict.status, "PERSISTENT_DISABLED_SWITCH")
        self.assertTrue(verdict.is_valid)
        self.assertTrue(verdict.is_persistent)
        self.assertTrue(verdict.disable_switch_active)
        self.assertTrue(verdict.service_in_runlevel)

    def test_fixture_invalid_ordering(self):
        path = FIXTURES_DIR / "boot-persistence-invalid-ordering.json"
        data = json.loads(path.read_text())
        verdict = evaluate_boot_persistence(data)
        self.assertEqual(verdict.status, "INVALID_ORDERING")
        self.assertFalse(verdict.is_valid)
        self.assertIn("invalid_runlevel_ordering_detected", verdict.failures)

    def test_fixture_runtime_only(self):
        path = FIXTURES_DIR / "boot-persistence-runtime-only.json"
        data = json.loads(path.read_text())
        verdict = evaluate_boot_persistence(data)
        self.assertEqual(verdict.status, "RUNTIME_ONLY")
        self.assertTrue(verdict.is_valid)
        self.assertFalse(verdict.is_persistent)

    def test_fixture_unconfigured(self):
        path = FIXTURES_DIR / "boot-persistence-unconfigured.json"
        data = json.loads(path.read_text())
        verdict = evaluate_boot_persistence(data)
        self.assertEqual(verdict.status, "UNCONFIGURED")
        self.assertTrue(verdict.is_valid)
        self.assertFalse(verdict.is_persistent)

    def test_cli_invocation(self):
        path = FIXTURES_DIR / "boot-persistence-valid-enabled.json"
        res = subprocess.run(
            [sys.executable, str(TOOL_PATH), str(path), "--init-script", str(INIT_SCRIPT_PATH)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0)
        parsed = json.loads(res.stdout)
        self.assertEqual(parsed["status"], "PERSISTENT_ENABLED")


if __name__ == "__main__":
    unittest.main()
