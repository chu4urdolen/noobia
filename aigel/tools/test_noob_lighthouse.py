#!/usr/bin/env python3
"""Unit tests for the Noob Lighthouse LAN presence and service beacon."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from noob_lighthouse import (
    KNOWN_INHABITANTS,
    format_status_line,
    load_roster,
    parse_ping_rtt,
    summarize_beacon_results,
)


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


class TestLoadRoster(unittest.TestCase):
    """The shared roster config, its fallbacks, and the env override."""

    def setUp(self) -> None:
        self._old_env = __import__("os").environ.pop("LIGHTHOUSE_ROSTER", None)

    def tearDown(self) -> None:
        if self._old_env is None:
            __import__("os").environ.pop("LIGHTHOUSE_ROSTER", None)
        else:
            __import__("os").environ["LIGHTHOUSE_ROSTER"] = self._old_env

    def test_explicit_path_wins(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump({"inhabitants": {"vader": {"ip": "192.168.100.99", "role": "test"}}}, handle)
            name = handle.name
        try:
            roster = load_roster(name)
            self.assertEqual(set(roster), {"vader"})
            self.assertEqual(roster["vader"]["ip"], "192.168.100.99")
        finally:
            Path(name).unlink()

    def test_env_override_beats_default(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump({"inhabitants": {"env_node": {"ip": "192.168.100.88"}}}, handle)
            name = handle.name
        try:
            os.environ["LIGHTHOUSE_ROSTER"] = name
            roster = load_roster()
            self.assertEqual(set(roster), {"env_node"})
        finally:
            os.environ.pop("LIGHTHOUSE_ROSTER", None)
            Path(name).unlink()

    def test_explicit_path_beats_env(self) -> None:
        env_name = None
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump({"inhabitants": {"env_node": {"ip": "192.168.100.88"}}}, handle)
            env_name = handle.name
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump({"inhabitants": {"path_node": {"ip": "192.168.100.77"}}}, handle)
            path_name = handle.name
        try:
            os.environ["LIGHTHOUSE_ROSTER"] = env_name
            roster = load_roster(path_name)
            self.assertEqual(set(roster), {"path_node"})
        finally:
            os.environ.pop("LIGHTHOUSE_ROSTER", None)
            Path(env_name).unlink()
            Path(path_name).unlink()

    def test_missing_file_falls_back_to_builtin(self) -> None:
        roster = load_roster("/nonexistent/roster.json")
        self.assertEqual(set(roster), set(KNOWN_INHABITANTS))

    def test_malformed_file_falls_back_to_builtin(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            handle.write("{ this is not json")
            name = handle.name
        try:
            roster = load_roster(name)
            self.assertEqual(set(roster), set(KNOWN_INHABITANTS))
        finally:
            Path(name).unlink()

    def test_entry_without_ip_rejected(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump({"inhabitants": {"broken": {"role": "no ip here"}}}, handle)
            name = handle.name
        try:
            roster = load_roster(name)
            self.assertEqual(set(roster), set(KNOWN_INHABITANTS))
        finally:
            Path(name).unlink()


class TestParsePingRtt(unittest.TestCase):
    def test_extracts_average(self) -> None:
        stdout = (
            "64 bytes from 8.8.8.8 icmp_seq=1 ttl=118 time=1.23 ms\n\n"
            "--- 8.8.8.8 ping statistics ---\n"
            "1 packets transmitted, 1 received, 0% packet loss, time 0ms\n"
            "rtt min/avg/max/mdev = 1.234/1.234/1.234/0.000\n"
        )
        self.assertAlmostEqual(parse_ping_rtt(stdout), 1.234)

    def test_no_statistics_returns_none(self) -> None:
        self.assertIsNone(parse_ping_rtt("0 packets transmitted, 1 received"))

    def test_empty_returns_none(self) -> None:
        self.assertIsNone(parse_ping_rtt(""))


class TestFormatStatusLine(unittest.TestCase):
    def base(self, **overrides) -> dict:
        res = {
            "nexus_ready": False,
            "online_count": 0,
            "total_count": 5,
            "online": [],
            "offline": ["argus", "gateway", "lynx", "nexus", "rose"],
            "inhabitants": {},
        }
        res.update(overrides)
        return res

    def test_empty_online_reads_as_none(self) -> None:
        line = format_status_line(self.base())
        self.assertIn("online=(none)", line)

    def test_offline_listed_when_present(self) -> None:
        line = format_status_line(self.base())
        self.assertIn("offline=argus,gateway,lynx,nexus,rose", line)

    def test_rtt_bits_and_none_offline(self) -> None:
        res = self.base(
            nexus_ready=True,
            online_count=2,
            online=["gateway", "nexus"],
            offline=[],
            inhabitants={
                "gateway": {"rtt_ms": 1.2},
                "nexus": {"rtt_ms": 12.7},
            },
        )
        line = format_status_line(res)
        self.assertIn("rtt=gateway=1ms,nexus=12ms", line)
        self.assertIn("offline=(none)", line)


if __name__ == "__main__":
    unittest.main()
