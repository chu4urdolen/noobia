#!/usr/bin/env python3
"""Unit tests for Nexus Network Defense Audit & Noobia Wi-Fi Watchdog."""

import unittest

from nexus_net_guard import (
    REQUIRED_SYSCTLS,
    evaluate_fail2ban,
    evaluate_noobia_wifi,
    evaluate_ufw_status,
    parse_sysctl_hardening,
    evaluate_listeners,
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


if __name__ == "__main__":
    unittest.main()
