#!/usr/bin/env python3
"""LNX-25: network tools touch only authorized targets, and every decision is logged."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lynx_tool_policy as p  # noqa: E402

NAMES = {"nexus.lan": ["192.168.100.106"], "example.org": ["93.184.215.14"],
         "sneaky.lan": ["192.168.100.5", "10.0.0.9"], "router.other": ["10.1.1.1"]}


def resolver(name, _port):
    if name not in NAMES:
        raise OSError("no such host")
    return [(2, 1, 6, "", (ip, 0)) for ip in NAMES[name]]


class PolicyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.policy = Path(self.tmp.name) / "tool-policy.json"
        self.log = Path(self.tmp.name) / "audit.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def ask(self, action, target=None):
        return p.authorize("test", action, target, policy_path=self.policy, log_path=self.log, resolver=resolver)

    def test_probing_only_lynx_and_the_noobia_lan(self):
        self.assertTrue(self.ask("port-scan", "192.168.100.106")[0])
        self.assertTrue(self.ask("port-scan", "nexus.lan")[0])
        self.assertTrue(self.ask("vuln-check", "127.0.0.1")[0])
        ok, why = self.ask("port-scan", "example.org")
        self.assertFalse(ok)
        self.assertIn("rule 7", why)
        self.assertFalse(self.ask("vuln-check", "8.8.8.8")[0])

    def test_a_name_hiding_an_outside_address_is_refused(self):
        self.assertFalse(self.ask("port-scan", "sneaky.lan")[0])

    def test_path_checks_may_reach_the_internet_not_other_private_nets(self):
        self.assertTrue(self.ask("traceroute", "8.8.8.8")[0])
        self.assertTrue(self.ask("ssl-audit", "example.org")[0])
        self.assertFalse(self.ask("traceroute", "router.other")[0])
        self.assertFalse(self.ask("traceroute", "nowhere.invalid")[0])

    def test_packet_capture_off_until_a_person_allows_it(self):
        ok, why = self.ask("packet-sample")
        self.assertFalse(ok)
        self.assertIn("allow_packet_capture", why)
        self.policy.write_text(json.dumps({"allow_packet_capture": True}))
        self.assertTrue(self.ask("packet-sample")[0])

    def test_passive_views_need_nothing_unknown_is_refused(self):
        self.assertTrue(self.ask("lan-sweep")[0])
        self.assertFalse(self.ask("arp-spoof", "192.168.100.1")[0])

    def test_broken_policy_fails_closed_except_passive(self):
        self.policy.write_text("{not json")
        self.assertFalse(self.ask("port-scan", "192.168.100.106")[0])
        self.assertTrue(self.ask("net-ifaces")[0])

    def test_custom_networks(self):
        self.policy.write_text(json.dumps({"authorized_networks": ["10.1.1.0/24"]}))
        self.assertTrue(self.ask("port-scan", "router.other")[0])
        self.assertFalse(self.ask("port-scan", "192.168.100.106")[0])

    def test_every_decision_is_logged(self):
        self.ask("port-scan", "example.org")
        self.ask("lan-sweep")
        rows = [json.loads(l) for l in self.log.read_text().splitlines()]
        self.assertEqual([(r["action"], r["allowed"]) for r in rows], [("port-scan", False), ("lan-sweep", True)])
        self.assertEqual(rows[0]["addresses"], ["93.184.215.14"])
        self.assertEqual(oct(self.log.stat().st_mode & 0o777), "0o600")


if __name__ == "__main__":
    unittest.main()
