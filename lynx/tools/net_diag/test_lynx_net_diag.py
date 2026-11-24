"""Unit tests for Lynx autonomous network diagnostic toolkit."""

from __future__ import annotations

import unittest
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


if __name__ == "__main__":
    unittest.main()
