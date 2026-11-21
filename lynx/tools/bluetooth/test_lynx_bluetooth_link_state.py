#!/usr/bin/env python3
"""Unit tests for lynx_bluetooth_link_state.py."""

import json
from pathlib import Path
import subprocess
import sys
import unittest

from lynx_bluetooth_link_state import (
    evaluate_bluetooth_link_state,
    parse_bluetoothctl_show,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
TOOL_PATH = Path(__file__).resolve().parent / "lynx_bluetooth_link_state.py"


class TestLynxBluetoothLinkState(unittest.TestCase):
    def test_link_state_radio_off(self):
        fixture_path = FIXTURES_DIR / "link-state-radio-off.json"
        data = json.loads(fixture_path.read_text())
        verdict = evaluate_bluetooth_link_state(data)

        self.assertEqual(verdict.status, "RADIO_OFF")
        self.assertTrue(verdict.is_valid)
        self.assertFalse(verdict.radio_powered)
        self.assertFalse(verdict.supervisor_running)
        self.assertEqual(verdict.active_connections_count, 0)
        self.assertEqual(len(verdict.connected_peers), 0)
        self.assertEqual(len(verdict.failures), 0)
        self.assertIn("powered off", verdict.summary)

    def test_link_state_ready_idle(self):
        fixture_path = FIXTURES_DIR / "link-state-ready-idle.json"
        data = json.loads(fixture_path.read_text())
        verdict = evaluate_bluetooth_link_state(data)

        self.assertEqual(verdict.status, "READY_UNLINKED")
        self.assertTrue(verdict.is_valid)
        self.assertTrue(verdict.radio_powered)
        self.assertTrue(verdict.supervisor_running)
        self.assertEqual(verdict.active_connections_count, 0)
        self.assertEqual(len(verdict.connected_peers), 0)
        self.assertIn("ready", verdict.summary)

    def test_link_state_connected_peer(self):
        fixture_path = FIXTURES_DIR / "link-state-connected-peer.json"
        data = json.loads(fixture_path.read_text())
        verdict = evaluate_bluetooth_link_state(data)

        self.assertEqual(verdict.status, "CONNECTED")
        self.assertTrue(verdict.is_valid)
        self.assertTrue(verdict.radio_powered)
        self.assertTrue(verdict.supervisor_running)
        self.assertEqual(verdict.active_connections_count, 1)
        self.assertEqual(len(verdict.connected_peers), 1)
        peer = verdict.connected_peers[0]
        self.assertEqual(peer["mac_address"], "00:1A:7D:DA:71:13")
        self.assertEqual(peer["device_name"], "Nexus-Client-BLE")
        self.assertTrue(peer["connected"])
        self.assertIn("1 connected peer", verdict.summary)

    def test_link_state_degraded(self):
        fixture_path = FIXTURES_DIR / "link-state-degraded.json"
        data = json.loads(fixture_path.read_text())
        verdict = evaluate_bluetooth_link_state(data)

        self.assertEqual(verdict.status, "DEGRADED")
        self.assertFalse(verdict.is_valid)
        self.assertIn("inconsistent_service_or_controller_state", verdict.failures)

    def test_link_state_unsafe_runlevel(self):
        fixture_path = FIXTURES_DIR / "link-state-unsafe-runlevel.json"
        data = json.loads(fixture_path.read_text())
        verdict = evaluate_bluetooth_link_state(data)

        self.assertEqual(verdict.status, "UNSAFE_CONFIG")
        self.assertFalse(verdict.is_valid)
        self.assertIn("lynx-bluetooth_in_default_runlevel_forbidden", verdict.failures)

    def test_link_state_unsafe_pairable(self):
        fixture_path = FIXTURES_DIR / "link-state-unsafe-pairable.json"
        data = json.loads(fixture_path.read_text())
        verdict = evaluate_bluetooth_link_state(data)

        self.assertEqual(verdict.status, "UNSAFE_CONFIG")
        self.assertFalse(verdict.is_valid)
        self.assertIn("pairable_mode_is_active_expected_disabled", verdict.failures)

    def test_link_state_absent_data(self):
        verdict = evaluate_bluetooth_link_state(None)
        self.assertEqual(verdict.status, "ABSENT")
        self.assertFalse(verdict.is_valid)
        self.assertIn("missing_data", verdict.failures)

        verdict_empty = evaluate_bluetooth_link_state({})
        self.assertEqual(verdict_empty.status, "ABSENT")
        self.assertFalse(verdict_empty.is_valid)

    def test_parse_bluetoothctl_show(self):
        sample_output = """
Controller F4:2A:7D:01:23:45 (public)
\tName: lynx-ble
\tAlias: lynx-ble
\tClass: 0x00000000
\tPowered: yes
\tDiscoverable: no
\tPairable: no
\tUUID: Generic Attribute Profile (00001801-0000-1000-8000-00805f9b34fb)
\tModalias: usb:v1D6Bp0246d0537
"""
        info = parse_bluetoothctl_show(sample_output)
        self.assertEqual(info["controller_mac"], "F4:2A:7D:01:23:45")
        self.assertEqual(info["name"], "lynx-ble")
        self.assertTrue(info["powered"])
        self.assertFalse(info["discoverable"])
        self.assertFalse(info["pairable"])

    def test_cli_fixture_run(self):
        fixture_path = FIXTURES_DIR / "link-state-radio-off.json"
        res = subprocess.run(
            [sys.executable, str(TOOL_PATH), str(fixture_path)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0)
        parsed = json.loads(res.stdout)
        self.assertEqual(parsed["status"], "RADIO_OFF")
        self.assertTrue(parsed["is_valid"])

    def test_cli_live_gate_refusal(self):
        res = subprocess.run(
            [sys.executable, str(TOOL_PATH), "--live"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 2)
        parsed_err = json.loads(res.stderr)
        self.assertIn("refusing live execution", parsed_err["error"])

    def test_disable_switch_active(self):
        data = {"disabled_by_switch": True, "error": "disabled"}
        verdict = evaluate_bluetooth_link_state(data)
        self.assertEqual(verdict.status, "DISABLED_BY_SWITCH")
        self.assertFalse(verdict.is_valid)
        self.assertIn("disabled_by_switch", verdict.failures)


if __name__ == "__main__":
    unittest.main()
