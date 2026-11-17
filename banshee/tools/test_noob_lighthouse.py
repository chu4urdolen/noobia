#!/usr/bin/env python3
"""Unit tests for the Noob Lighthouse LAN presence and service beacon."""

import unittest

from noob_lighthouse import KNOWN_INHABITANTS, summarize_beacon_results


def make_probes(**overrides: dict) -> dict[str, dict]:
    """Build a full probes fixture from KNOWN_INHABITANTS with per-name overrides."""
    probes = {
        name: {
            "ip": info["ip"],
            "role": info["role"],
            "ping_ok": True,
            "open_ports": list(info["tcp_ports"]),
        }
        for name, info in KNOWN_INHABITANTS.items()
    }
    for name, record in overrides.items():
        probes[name] = record
    return probes


class TestKnownInhabitants(unittest.TestCase):
    def test_roster_members(self) -> None:
        self.assertEqual(
            set(KNOWN_INHABITANTS),
            {"gateway", "nexus", "lynx", "argus", "rose"},
        )

    def test_roster_ips_and_ports(self) -> None:
        self.assertEqual(KNOWN_INHABITANTS["gateway"]["ip"], "192.168.100.1")
        self.assertEqual(KNOWN_INHABITANTS["gateway"]["tcp_ports"], [])
        self.assertEqual(KNOWN_INHABITANTS["nexus"]["ip"], "192.168.100.106")
        self.assertEqual(KNOWN_INHABITANTS["nexus"]["tcp_ports"], [22, 8080, 48101])
        self.assertEqual(KNOWN_INHABITANTS["lynx"]["ip"], "192.168.100.107")
        self.assertEqual(KNOWN_INHABITANTS["lynx"]["tcp_ports"], [2222, 4243])
        self.assertEqual(KNOWN_INHABITANTS["argus"]["ip"], "192.168.100.105")
        self.assertEqual(KNOWN_INHABITANTS["argus"]["tcp_ports"], [22, 47200, 47201])
        self.assertEqual(KNOWN_INHABITANTS["rose"]["ip"], "192.168.100.7")
        self.assertEqual(KNOWN_INHABITANTS["rose"]["tcp_ports"], [22, 47300, 47301])


class TestSummarizeBeaconResults(unittest.TestCase):
    def test_all_inhabitants_online(self) -> None:
        res = summarize_beacon_results(make_probes())
        self.assertTrue(res["nexus_ready"])
        self.assertEqual(res["online_count"], 5)
        self.assertEqual(res["total_count"], 5)
        self.assertEqual(res["offline"], [])
        self.assertEqual(res["online"], ["argus", "gateway", "lynx", "nexus", "rose"])

    def test_live_lan_state_gateway_nexus_lynx_online(self) -> None:
        probes = make_probes(
            argus={"ip": "192.168.100.105", "role": "Argus (Historian)", "ping_ok": False, "open_ports": []},
            rose={"ip": "192.168.100.7", "role": "Rose", "ping_ok": False, "open_ports": []},
        )
        res = summarize_beacon_results(probes)
        self.assertTrue(res["nexus_ready"])
        self.assertEqual(res["online"], ["gateway", "lynx", "nexus"])
        self.assertEqual(res["offline"], ["argus", "rose"])
        self.assertEqual(res["online_count"], 3)
        self.assertEqual(res["total_count"], 5)

    def test_open_ports_count_as_online_when_ping_fails(self) -> None:
        probes = make_probes(
            lynx={"ip": "192.168.100.107", "role": "Lynx (Alpine / NRP/1)", "ping_ok": False, "open_ports": [2222]},
        )
        res = summarize_beacon_results(probes)
        self.assertIn("lynx", res["online"])
        self.assertNotIn("lynx", res["offline"])
        self.assertEqual(res["online_count"], 5)
        self.assertEqual(res["offline"], [])

    def test_gateway_offline_disables_nexus_ready(self) -> None:
        probes = make_probes(
            gateway={"ip": "192.168.100.1", "role": "Noobia Wi-Fi Router", "ping_ok": False, "open_ports": []},
        )
        res = summarize_beacon_results(probes)
        self.assertFalse(res["nexus_ready"])
        self.assertIn("gateway", res["offline"])

    def test_nexus_offline_disables_nexus_ready(self) -> None:
        probes = make_probes(
            nexus={"ip": "192.168.100.106", "role": "Nexus (Aria, Banshee, Dushich)", "ping_ok": False, "open_ports": []},
        )
        res = summarize_beacon_results(probes)
        self.assertFalse(res["nexus_ready"])
        self.assertIn("nexus", res["offline"])

    def test_inhabitants_echoed_back(self) -> None:
        probes = make_probes()
        res = summarize_beacon_results(probes)
        self.assertIs(res["inhabitants"], probes)


if __name__ == "__main__":
    unittest.main()
