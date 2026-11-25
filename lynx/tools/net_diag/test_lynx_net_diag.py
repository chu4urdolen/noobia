"""Unit tests for Lynx autonomous network diagnostic toolkit."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from lynx.tools.net_diag import lynx_net_diag as diag


class TestNetDiag(unittest.TestCase):
    @patch("lynx.tools.net_diag.lynx_net_diag.run_cmd")
    def test_wifi_recon_parser(self, mock_cmd):
        mock_output = """
BSS 90:91:64:21:0f:3d(on wlan0) -- associated
\tTSF: 100 usec
\tfreq: 2437.0
\tsignal: -62.00 dBm
\tSSID: Noobia
\tRSN:\t * Version: 1
BSS aa:bb:cc:dd:ee:ff(on wlan0)
\tfreq: 5180.0
\tsignal: -81.00 dBm
\tSSID: NeighborNet
"""
        mock_cmd.return_value = (0, mock_output, "")
        res = diag.wifi_recon("wlan0")
        self.assertTrue(res["ok"])
        self.assertEqual(res["count"], 2)
        self.assertEqual(res["networks"][0]["ssid"], "Noobia")
        self.assertTrue(res["networks"][0]["associated"])
        self.assertEqual(res["networks"][0]["signal_dbm"], -62.0)
        self.assertEqual(res["networks"][0]["security"], "WPA2/WPA3")
        self.assertEqual(res["networks"][1]["ssid"], "NeighborNet")
        self.assertIn("Wi-Fi airspace scan detected 2 networks", res["sentence"])

    @patch("lynx.tools.net_diag.lynx_net_diag.run_cmd")
    def test_lan_sweep_parser(self, mock_cmd):
        mock_output = """
192.168.100.1 dev wlan0 lladdr 48:ad:08:d8:1f:6c REACHABLE
192.168.100.106 dev wlan0 lladdr 40:a5:ef:5f:66:f1 REACHABLE
"""
        mock_cmd.return_value = (0, mock_output, "")
        res = diag.lan_sweep("wlan0")
        self.assertTrue(res["ok"])
        self.assertEqual(res["count"], 2)
        self.assertEqual(res["neighbors"][0]["ip"], "192.168.100.1")
        self.assertTrue(res["neighbors"][0]["is_gateway"])
        self.assertEqual(res["neighbors"][1]["ip"], "192.168.100.106")
        self.assertFalse(res["neighbors"][1]["is_gateway"])
        self.assertIn("Local network sweep on wlan0 found 2 live devices", res["sentence"])

    @patch("lynx.tools.net_diag.lynx_net_diag.run_cmd")
    def test_net_ifaces_parser(self, mock_cmd):
        mock_output = """
1: lo    inet 127.0.0.1/8 scope host lo
2: wlan0    inet 192.168.100.107/24 brd 192.168.100.255 scope global wlan0
3: dummy0    inet 10.0.0.1/24 scope global dummy0
"""
        mock_cmd.return_value = (0, mock_output, "")
        res = diag.net_ifaces()
        self.assertTrue(res["ok"])
        self.assertEqual(res["count"], 3)
        self.assertEqual(res["interfaces"][1]["name"], "wlan0")
        self.assertEqual(res["interfaces"][1]["ip"], "192.168.100.107")
        self.assertIn("There are 3 active network interfaces", res["sentence"])

    @patch("lynx.tools.net_diag.lynx_net_diag.run_cmd")
    def test_vuln_check_clean(self, mock_cmd):
        mock_output = "tcp 0 0 0.0.0.0:22 0.0.0.0:* LISTEN\ntcp 0 0 0.0.0.0:2222 0.0.0.0:* LISTEN"
        mock_cmd.return_value = (0, mock_output, "")
        res = diag.vuln_check("127.0.0.1")
        self.assertTrue(res["ok"])
        self.assertTrue(res["clean"])
        self.assertIn("Security posture audit on 127.0.0.1: clean", res["sentence"])

    @patch("lynx.tools.net_diag.lynx_net_diag.run_cmd")
    def test_dns_audit_parser(self, mock_cmd):
        mock_output = """
;; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 1234
;; Query time: 14 msec
;; SERVER: 192.168.100.1#53(192.168.100.1)
"""
        mock_cmd.return_value = (0, mock_output, "")
        res = diag.dns_audit("google.com")
        self.assertTrue(res["ok"])
        self.assertEqual(res["query_time_ms"], 14)
        self.assertEqual(res["server"], "192.168.100.1")
        self.assertEqual(res["status"], "NOERROR")
        self.assertIn("returned NOERROR in 14 ms", res["sentence"])

    def test_action_lock_concurrency(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("lynx.tools.net_diag.lynx_net_diag.LOCK_DIR", Path(tmpdir)):
                lock1 = diag.ActionLock("test_action")
                lock2 = diag.ActionLock("test_action")
                self.assertTrue(lock1.acquire())
                self.assertFalse(lock2.acquire())
                lock1.release()
                self.assertTrue(lock2.acquire())
                lock2.release()



class PolicyGateTest(unittest.TestCase):
    """LNX-25: the policy is asked before the lock and the fork."""
    def test_targets_per_action(self):
        import argparse
        ns = argparse.Namespace(target="192.168.100.106", host="example.org", server=None, domain="noobia.org")
        self.assertEqual(diag.policy_target("port-scan", ns), "192.168.100.106")
        self.assertEqual(diag.policy_target("ssl-audit", ns), "example.org")
        self.assertEqual(diag.policy_target("dns-audit", ns), "noobia.org")
        self.assertIsNone(diag.policy_target("lan-sweep", ns))

    def test_outside_port_scan_is_refused_before_running(self):
        import io, json, sys as _sys
        from contextlib import redirect_stdout
        with tempfile.TemporaryDirectory() as d, \
             patch.dict("os.environ", {"LYNX_TOOL_POLICY_LOG": d + "/log.jsonl"}), \
             patch.object(diag, "port_scan", side_effect=AssertionError("must not run")), \
             patch.object(_sys, "argv", ["lynx-net-diag", "port-scan", "8.8.8.8"]):
            out = io.StringIO()
            with redirect_stdout(out), self.assertRaises(SystemExit) as stop:
                diag.main()
            self.assertEqual(stop.exception.code, 3)
            self.assertTrue(json.loads(out.getvalue())["refused"])

if __name__ == "__main__":
    unittest.main()
