#!/usr/bin/env python3
"""Unit tests for Nexus Network Defense Audit & Noobia Wi-Fi Watchdog."""

import hashlib
import tempfile
import unittest
from pathlib import Path

from nexus_net_guard import (
    DEFAULT_DEFENSE_CONFIGS,
    REQUIRED_SYSCTLS,
    evaluate_arp_neighbors,
    evaluate_config_integrity,
    evaluate_fail2ban,
    evaluate_listeners,
    derive_verdict,
    evaluate_noobia_wifi,
    evaluate_ufw_status,
    evaluate_wifi_signal,
    parse_sysctl_hardening,
)


class TestNexusNetGuard(unittest.TestCase):
    def test_parse_sysctl_hardening_healthy(self) -> None:
        result = parse_sysctl_hardening(dict(REQUIRED_SYSCTLS))
        self.assertTrue(result["ok"])
        self.assertEqual(result["missing_or_weak"], [])
        self.assertTrue(all(result["checks"].values()))

    def test_parse_sysctl_hardening_detects_weak_setting(self) -> None:
        bad = dict(REQUIRED_SYSCTLS)
        bad["net.ipv4.conf.all.accept_redirects"] = "1"
        bad.pop("net.ipv4.tcp_rfc1337")
        result = parse_sysctl_hardening(bad)
        self.assertFalse(result["ok"])
        self.assertIn("net.ipv4.conf.all.accept_redirects", result["missing_or_weak"])
        self.assertIn("net.ipv4.tcp_rfc1337", result["missing_or_weak"])

    def test_evaluate_ufw_status_healthy(self) -> None:
        sample = """Status: active
Logging: on (low)
Default: deny (incoming), allow (outgoing), disabled (routed)

To                         Action      From
--                         ------      ----
Anywhere                   ALLOW IN    192.168.100.0/24           # Trusted Noobia Wi-Fi Noobs
Anywhere                   ALLOW IN    192.168.4.0/24             # Trusted Lolth Spiderbot AP
22/tcp                     LIMIT IN    Anywhere                   # Rate-limited SSH fallback
"""
        res = evaluate_ufw_status(sample)
        self.assertTrue(res["ok"])
        self.assertTrue(res["status_ok"])
        self.assertTrue(res["default_incoming_ok"])
        self.assertEqual(res["subnet_ok"], {"192.168.100.0/24": True, "192.168.4.0/24": True})
        self.assertTrue(res["ssh_limit_ok"])

    def test_evaluate_ufw_status_inactive_or_missing_noobia_subnet(self) -> None:
        res = evaluate_ufw_status("Status: inactive\n")
        self.assertFalse(res["ok"])
        self.assertFalse(res["status_ok"])

    def test_evaluate_noobia_wifi_healthy_and_degraded(self) -> None:
        nmcli_ok = "wlx40a5ef5f66f1:connected:Noobia MT7612U\n"
        ip_ok = "wlx40a5ef5f66f1  UP             192.168.100.106/24\n"
        ps_ok = "Power save: off\n"
        res = evaluate_noobia_wifi(nmcli_ok, ip_ok, ps_ok)
        self.assertTrue(res["ok"])

        res_bad_ps = evaluate_noobia_wifi(nmcli_ok, ip_ok, "Power save: on\n")
        self.assertFalse(res_bad_ps["ok"])
        self.assertFalse(res_bad_ps["powersave_ok"])

    def test_evaluate_fail2ban(self) -> None:
        res = evaluate_fail2ban("active\n", "Status for the jail: sshd\n")
        self.assertTrue(res["ok"])
        res_bad = evaluate_fail2ban("inactive\n", "")
        self.assertFalse(res_bad["ok"])

    # Listener tests
    def test_evaluate_listeners_healthy(self) -> None:
        ss = (
            "tcp   LISTEN  0   128  0.0.0.0:22   *:*   users:"  # SSH
            "tcp   LISTEN  0   128  192.168.100.106:8080  *:*   users:"  # inference proxy
            "tcp   LISTEN  0   128  127.0.0.1:11434  *:*   users:"  # ollama
        )
        res = evaluate_listeners(ss)
        self.assertTrue(res["ok"])
        self.assertTrue(res["ssh_listening"])
        self.assertTrue(res["inference_proxy_lan_ok"])
        self.assertTrue(res["ollama_localhost_only"])

    def test_evaluate_listeners_detects_exposed_ollama(self) -> None:
        ss = (
            "tcp   LISTEN  0   128  0.0.0.0:11434  *:*   users:"  # exposed ollama
            "tcp   LISTEN  0   128  0.0.0.0:22   *:*   users:"  # SSH
            "tcp   LISTEN  0   128  192.168.100.106:8080  *:*   users:"  # inference proxy
        )
        res = evaluate_listeners(ss)
        self.assertFalse(res["ok"])
        self.assertTrue(res["ssh_listening"])
        self.assertTrue(res["inference_proxy_lan_ok"])
        self.assertFalse(res["ollama_localhost_only"])


class TestEvaluateWifiSignal(unittest.TestCase):
    def test_not_connected(self) -> None:
        res = evaluate_wifi_signal("Not connected.")
        self.assertFalse(res["ok"])
        self.assertIsNone(res["rssi_dbm"])
        self.assertFalse(res["strong_signal"])

    def test_strong_signal(self) -> None:
        text = (
            "Connected to 90:91:64:21:0f:3d (on wlx40a5ef5f66f1)\n"
            "\tSSID: Noobia\n"
            "\tsignal: -52 dBm\n"
        )
        res = evaluate_wifi_signal(text)
        self.assertTrue(res["ok"])
        self.assertEqual(res["rssi_dbm"], -52)
        self.assertTrue(res["strong_signal"])

    def test_weak_signal(self) -> None:
        res = evaluate_wifi_signal("Connected to AA:BB:CC:DD:EE:FF\n\tsignal: -82 dBm\n")
        self.assertFalse(res["ok"])
        self.assertEqual(res["rssi_dbm"], -82)
        self.assertFalse(res["strong_signal"])

    def test_connected_without_signal_line(self) -> None:
        text = "Connected to 90:91:64:21:0f:3d (on wlx40a5ef5f66f1)\n\tSSID: Noobia\n"
        res = evaluate_wifi_signal(text)
        self.assertTrue(res["ok"])
        self.assertIsNone(res["rssi_dbm"])
        self.assertTrue(res["strong_signal"])

    def test_boundary_rssi_minus_75(self) -> None:
        res = evaluate_wifi_signal("signal: -75 dBm\n")
        self.assertTrue(res["ok"])
        self.assertTrue(res["strong_signal"])
        res = evaluate_wifi_signal("signal: -76 dBm\n")
        self.assertFalse(res["ok"])
        self.assertFalse(res["strong_signal"])


class TestEvaluateArpNeighbors(unittest.TestCase):
    def test_healthy_neighbors(self) -> None:
        text = (
            "192.168.100.1 lladdr 48:ad:08:d8:1f:6c REACHABLE\n"
            "192.168.100.107 lladdr AC:C0:48:6D:F1:FB STALE\n"
            "192.168.100.7 lladdr aa:bb:cc:dd:ee:03 DELAY\n"
        )
        res = evaluate_arp_neighbors(text)
        self.assertTrue(res["ok"])
        self.assertTrue(res["gateway_present"])
        self.assertEqual(res["neighbor_count"], 3)
        self.assertEqual(res["duplicate_macs"], [])

    def test_detects_arp_spoofing_duplicate_mac(self) -> None:
        text = (
            "192.168.100.1 lladdr 48:ad:08:d8:1f:6c REACHABLE\n"
            "192.168.100.107 lladdr aa:bb:cc:dd:ee:02 STALE\n"
            "192.168.100.200 lladdr AA:BB:CC:DD:EE:02 REACHABLE\n"
        )
        res = evaluate_arp_neighbors(text)
        self.assertFalse(res["ok"])
        self.assertTrue(res["gateway_present"])
        self.assertEqual(res["duplicate_macs"], ["aa:bb:cc:dd:ee:02"])

    def test_missing_gateway(self) -> None:
        text = "192.168.100.107 lladdr AC:C0:48:6D:F1:FB REACHABLE\n"
        res = evaluate_arp_neighbors(text)
        self.assertFalse(res["ok"])
        self.assertFalse(res["gateway_present"])
        self.assertEqual(res["neighbor_count"], 1)
        self.assertEqual(res["duplicate_macs"], [])

    def test_ignores_failed_entries_without_lladdr(self) -> None:
        text = (
            "192.168.100.1 lladdr 48:ad:08:d8:1f:6c REACHABLE\n"
            "192.168.100.99 FAILED\n"
        )
        res = evaluate_arp_neighbors(text)
        self.assertTrue(res["ok"])
        self.assertEqual(res["neighbor_count"], 1)


class TestEvaluateConfigIntegrity(unittest.TestCase):
    def test_healthy_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p1 = Path(tmp) / "a.conf"
            p2 = Path(tmp) / "b.conf"
            p1.write_text("alpha\n")
            p2.write_text("beta\n")
            res = evaluate_config_integrity((str(p1), str(p2)))
            self.assertTrue(res["ok"])
            self.assertEqual(res["missing"], [])
            self.assertEqual(
                res["sha256"][str(p1)],
                hashlib.sha256(b"alpha\n").hexdigest(),
            )
            self.assertEqual(
                res["sha256"][str(p2)],
                hashlib.sha256(b"beta\n").hexdigest(),
            )

    def test_missing_and_empty_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "good.conf"
            good.write_text("present\n")
            absent = str(Path(tmp) / "absent.conf")
            empty = Path(tmp) / "empty.conf"
            empty.touch()
            res = evaluate_config_integrity((str(good), absent, str(empty)))
            self.assertFalse(res["ok"])
            self.assertEqual(res["missing"], [absent, str(empty)])
            self.assertIsNone(res["sha256"][absent])
            self.assertIsNone(res["sha256"][str(empty)])
            self.assertEqual(res["sha256"][str(good)], hashlib.sha256(b"present\n").hexdigest())

    def test_default_defense_configs_constant(self) -> None:
        self.assertEqual(
            DEFAULT_DEFENSE_CONFIGS,
            (
                "/etc/NetworkManager/conf.d/90-noobia-wifi-powersave-off.conf",
                "/etc/fail2ban/jail.d/90-nexus-defense.local",
                "/etc/ssh/sshd_config.d/90-nexus-hardening.conf",
                "/etc/sysctl.d/90-nexus-network-security.conf",
            ),
        )


class TestDeriveVerdict(unittest.TestCase):
    """The top-level ok/warn/fail verdict with reasons."""

    def test_ok_when_all_healthy(self) -> None:
        sections = {"sysctls": {"ok": True}, "ufw": {"ok": True}}
        verdict, reasons = derive_verdict(healthy=True, healed=False, sections=sections, ping_ok=True)
        self.assertEqual(verdict, "ok")
        self.assertEqual(reasons, [])

    def test_warn_when_wifi_was_healed(self) -> None:
        sections = {"sysctls": {"ok": True}}
        verdict, reasons = derive_verdict(healthy=True, healed=True, sections=sections, ping_ok=True)
        self.assertEqual(verdict, "warn")
        self.assertTrue(any("auto-healed" in reason for reason in reasons))

    def test_fail_when_a_section_fails(self) -> None:
        sections = {"sysctls": {"ok": False, "missing": ["a", "b"]}, "ufw": {"ok": True}}
        verdict, reasons = derive_verdict(healthy=True, healed=False, sections=sections, ping_ok=True)
        self.assertEqual(verdict, "fail")
        self.assertTrue(any("sysctls failed" in reason and "a" in reason for reason in reasons))

    def test_fail_when_gateway_ping_fails(self) -> None:
        verdict, reasons = derive_verdict(healthy=True, healed=False, sections={}, ping_ok=False)
        self.assertEqual(verdict, "fail")
        self.assertIn("gateway ping failed", reasons)

    def test_fail_wins_over_healed(self) -> None:
        sections = {"ufw": {"ok": False}}
        verdict, reasons = derive_verdict(healthy=False, healed=True, sections=sections, ping_ok=True)
        self.assertEqual(verdict, "fail")
        self.assertTrue(any("ufw failed" in reason for reason in reasons))

    def test_missing_reason_capped_at_four(self) -> None:
        sections = {"x": {"ok": False, "missing": ["m1", "m2", "m3", "m4", "m5"]}}
        verdict, reasons = derive_verdict(healthy=False, healed=False, sections=sections, ping_ok=True)
        self.assertEqual(verdict, "fail")
        self.assertTrue(any("m1" in reason and "m5" not in reason for reason in reasons))


if __name__ == "__main__":
    unittest.main()
