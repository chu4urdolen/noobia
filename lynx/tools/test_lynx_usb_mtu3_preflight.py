#!/usr/bin/env python3
"""Offline unit tests for lynx_usb_mtu3_preflight.py."""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from lynx_usb_mtu3_preflight import (
    CONTROLLER_NAME,
    DEFAULT_LYNX_HOST,
    DEFAULT_LYNX_SSH_PORT,
    DUMMY_UDC_PREFIX,
    EXIT_BLOCKED,
    EXIT_ERROR,
    EXIT_LIVE_REFUSED,
    EXIT_READY,
    MIN_BATTERY_PERCENT,
    PINNED_MTU3_SHA256,
    PINNED_V53_BOOT_ID,
    LiveCollectionError,
    PreflightInputError,
    _live_script,
    build_ssh_command,
    evaluate_preflight,
    load_fixture,
    main,
)


def valid_observations() -> dict:
    return {
        "boot_id": PINNED_V53_BOOT_ID,
        "kernel_release": "5.10.149-android12-9-o-g311738fbb5a8",
        "mtu3_sha256": PINNED_MTU3_SHA256,
        "module_vermagic": "5.10.149-android12-9-o-g311738fbb5a8 SMP preempt mod_unload aarch64",
        "battery_percent": 65.0,
        "charging": True,
        "safe_power": True,
        "health_clear": True,
        "controller_present": True,
        "controller_bound_driver": "",
        "udc_devices": ["dummy_udc.0"],
    }


class PureLogicTests(unittest.TestCase):
    def test_all_pins_pass(self):
        obs = valid_observations()
        report = evaluate_preflight(obs)
        self.assertEqual(report["state"], "ready")
        self.assertTrue(report["ready"])
        self.assertEqual(report["blockers"], [])
        self.assertTrue(all(c["pass"] for c in report["checks"].values()))
        self.assertIn("side_effects", report)

    def test_boot_id_mismatch(self):
        obs = valid_observations()
        obs["boot_id"] = "deadbeef-0000-0000-0000-000000000000"
        report = evaluate_preflight(obs)
        self.assertEqual(report["state"], "blocked")
        self.assertFalse(report["ready"])
        self.assertIn("boot_id", report["blockers"])
        self.assertFalse(report["checks"]["boot_id"]["pass"])

    def test_mtu3_sha_mismatch(self):
        obs = valid_observations()
        obs["mtu3_sha256"] = "0" * 64
        report = evaluate_preflight(obs)
        self.assertEqual(report["state"], "blocked")
        self.assertIn("mtu3_sha", report["blockers"])

    def test_mtu3_sha_invalid_length(self):
        obs = valid_observations()
        obs["mtu3_sha256"] = "abc123"
        report = evaluate_preflight(obs)
        self.assertIn("mtu3_sha", report["blockers"])

    def test_vermagic_mismatch(self):
        obs = valid_observations()
        obs["module_vermagic"] = "6.1.0-generic SMP mod_unload aarch64"
        report = evaluate_preflight(obs)
        self.assertIn("vermagic", report["blockers"])

    def test_battery_below_min_gate(self):
        obs = valid_observations()
        obs["battery_percent"] = 49.9
        report = evaluate_preflight(obs)
        self.assertIn("battery", report["blockers"])

    def test_battery_out_of_range(self):
        obs = valid_observations()
        obs["battery_percent"] = 105.0
        report = evaluate_preflight(obs)
        self.assertIn("battery", report["blockers"])

        obs["battery_percent"] = -1.0
        report = evaluate_preflight(obs)
        self.assertIn("battery", report["blockers"])

    def test_power_discharging_without_safe_power(self):
        obs = valid_observations()
        obs["charging"] = False
        obs["safe_power"] = False
        report = evaluate_preflight(obs)
        self.assertIn("power", report["blockers"])

    def test_power_safe_power_when_not_charging(self):
        obs = valid_observations()
        obs["charging"] = False
        obs["safe_power"] = True
        report = evaluate_preflight(obs)
        self.assertTrue(report["checks"]["power"]["pass"])

    def test_health_not_clear(self):
        obs = valid_observations()
        obs["health_clear"] = False
        report = evaluate_preflight(obs)
        self.assertIn("health", report["blockers"])

    def test_controller_missing(self):
        obs = valid_observations()
        obs["controller_present"] = False
        report = evaluate_preflight(obs)
        self.assertIn("controller_unbound", report["blockers"])

    def test_controller_already_bound(self):
        obs = valid_observations()
        obs["controller_bound_driver"] = "mtu3"
        report = evaluate_preflight(obs)
        self.assertIn("controller_unbound", report["blockers"])

    def test_udc_empty(self):
        obs = valid_observations()
        obs["udc_devices"] = []
        report = evaluate_preflight(obs)
        self.assertIn("dummy_udc_only", report["blockers"])

    def test_udc_has_non_dummy(self):
        obs = valid_observations()
        obs["udc_devices"] = ["dummy_udc.0", "11201000.usb0"]
        report = evaluate_preflight(obs)
        self.assertIn("dummy_udc_only", report["blockers"])

    def test_missing_required_keys_raises(self):
        obs = valid_observations()
        del obs["boot_id"]
        with self.assertRaises(PreflightInputError):
            evaluate_preflight(obs)

    def test_wrong_type_raises(self):
        obs = valid_observations()
        obs["battery_percent"] = "sixty-five"
        with self.assertRaises(PreflightInputError):
            evaluate_preflight(obs)

        obs = valid_observations()
        obs["charging"] = "yes"
        with self.assertRaises(PreflightInputError):
            evaluate_preflight(obs)

        obs = valid_observations()
        obs["udc_devices"] = "dummy_udc.0"
        with self.assertRaises(PreflightInputError):
            evaluate_preflight(obs)


class FixtureAndCommandTests(unittest.TestCase):
    def test_fixture_loading(self):
        obs = valid_observations()
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as f:
            json.dump(obs, f)
            temp_path = f.name
        try:
            loaded = load_fixture(temp_path)
            self.assertEqual(loaded["boot_id"], obs["boot_id"])
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_fixture_loading_errors(self):
        with self.assertRaises(PreflightInputError):
            load_fixture("/nonexistent/file/path.json")

        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as f:
            f.write("not valid json")
            bad_json = f.name
        try:
            with self.assertRaises(PreflightInputError):
                load_fixture(bad_json)
        finally:
            Path(bad_json).unlink(missing_ok=True)

    def test_ssh_command_structure(self):
        cmd = build_ssh_command(
            host=DEFAULT_LYNX_HOST,
            port=DEFAULT_LYNX_SSH_PORT,
            script="echo test",
            key_path=Path("/noobia/lynx/secrets/nexus_lynx_ed25519"),
            known_hosts=Path("/noobia/lynx/secrets/lynx_known_hosts"),
            connect_timeout=5,
            command_timeout=20,
        )
        self.assertEqual(cmd[0], "ssh")
        self.assertIn("-o", cmd)
        self.assertIn("IdentitiesOnly=yes", cmd)
        self.assertIn("IdentityAgent=none", cmd)
        self.assertIn("StrictHostKeyChecking=yes", cmd)
        self.assertIn("-p", cmd)
        self.assertIn(str(DEFAULT_LYNX_SSH_PORT), cmd)
        self.assertIn(f"root@{DEFAULT_LYNX_HOST}", cmd)
        # Check command has timeout
        last_arg = cmd[-1]
        self.assertTrue(last_arg.startswith("timeout 20 sh -c"))

    def test_live_script_read_only(self):
        script = _live_script(DEFAULT_LYNX_HOST, DEFAULT_LYNX_SSH_PORT, "/vendor_dlkm/lib/modules/mtu3.ko")
        # Ensure only read-only tools are invoked and no mutating operations exist
        for dangerous in ["insmod", "rmmod", "modprobe", "reboot", "poweroff", "dd", "rm ", "tee "]:
            self.assertNotIn(dangerous, script)
        self.assertIn("sha256sum", script)
        self.assertIn("modinfo -F vermagic", script)
        self.assertIn("/proc/sys/kernel/random/boot_id", script)

    def test_live_script_traversal_rejected(self):
        with self.assertRaises(LiveCollectionError):
            _live_script(DEFAULT_LYNX_HOST, DEFAULT_LYNX_SSH_PORT, "/vendor_dlkm/../../etc/passwd")


class CLITests(unittest.TestCase):
    def test_live_without_allow_live_refused(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            exit_code = main(["--live"])
        self.assertEqual(exit_code, EXIT_LIVE_REFUSED)
        self.assertIn("refused: --live would contact Lynx", stderr.getvalue())

    def test_fixture_cli_ready(self):
        obs = valid_observations()
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as f:
            json.dump(obs, f)
            temp_path = f.name
        try:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["--fixture", temp_path])
            self.assertEqual(exit_code, EXIT_READY)
            self.assertIn("state=ready", stdout.getvalue())
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_fixture_cli_blocked_and_json(self):
        obs = valid_observations()
        obs["battery_percent"] = 30.0
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as f:
            json.dump(obs, f)
            temp_path = f.name
        try:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["--fixture", temp_path, "--json"])
            self.assertEqual(exit_code, EXIT_BLOCKED)
            data = json.loads(stdout.getvalue())
            self.assertEqual(data["state"], "blocked")
            self.assertIn("battery", data["blockers"])
        finally:
            Path(temp_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
