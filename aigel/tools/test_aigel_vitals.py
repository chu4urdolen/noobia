#!/usr/bin/env python3
"""Unit tests for Aigel's vitals board."""

import os
import tempfile
import unittest

from aigel_vitals import (
    derive_verdict,
    latest_line,
    parse_cpu_sample,
    parse_disk_sample,
    parse_mem_sample,
    parse_net_sample,
)

CPU_SAMPLE = (
    "2026-11-18T18:30:23.522Z cores: cpu0=38% cpu1=33% cpu2=32% cpu3=3% cpu4=32% cpu5=25% "
    "cpu6=65% cpu7=8% cpu8=5% cpu9=31% cpu10=6% cpu11=12% | top: top - 20:30:23 up 3:59, "
    "1 user, load average: 4.71, 3.33, 2.46 Tasks: 452 total, 3 running %Cpu(s): 32.1 us "
    "MiB Mem : 59134.2 total, 4554.4 free, 16040.9 used, 39081.9 buff/cache"
)
NET_SAMPLE = (
    "2026-11-18T18:30:17.133Z interfaces: 2: enp34s0: <NO-CARRIER,BROADCAST,UP> mtu 1500 "
    "state DOWN; 4: wlx40a5ef5f66f1: <BROADCAST,UP,LOWER_UP> mtu 1500 state UP | "
    "tcp(last 5): ESTAB 0 0 192.168.8.100:46592 146.75.1.91:https; | "
    "dns-8.8.8.8-rtt: 27.342/27.342/27.342/0.000 ms"
)
DISK_SAMPLE = (
    "2026-11-18T18:30:17.447Z mounts: /dev/nvme0n1p2: 12% used (1.5T free) "
    "/dev/loop0: 100% used (0 free) tmpfs: 1% used (29G free) /dev/nvme0n1p1: 1% used (1.1G free)"
)
MEM_SAMPLE = "2026-11-18T18:30:14.806Z ram: 15Gi / 57Gi used (4.3Gi free) | vram: 32607MiB / 27048MiB used (5064MiB free)"


class TestParsers(unittest.TestCase):
    def test_cpu(self) -> None:
        facts = parse_cpu_sample(CPU_SAMPLE)
        self.assertEqual(facts["timestamp"], "2026-11-18T18:30:23.522Z")
        self.assertEqual(facts["cores_count"], 12)
        self.assertEqual(facts["cores_max_pct"], 65)
        self.assertAlmostEqual(facts["cores_avg_pct"], 24.2)
        self.assertEqual(facts["load1"], 4.71)
        self.assertLess(facts["ram_free_pct"], 10)

    def test_net(self) -> None:
        facts = parse_net_sample(NET_SAMPLE)
        self.assertEqual(facts["wifi_state"], "UP")
        self.assertEqual(facts["dns_rtt_ms"], 27.342)

    def test_disk_skips_synthetic(self) -> None:
        facts = parse_disk_sample(DISK_SAMPLE)
        devices = [mount["device"] for mount in facts["mounts"]]
        self.assertEqual(devices, ["/dev/nvme0n1p2", "/dev/nvme0n1p1"])
        self.assertEqual(facts["max_used_pct"], 12)
        self.assertEqual(facts["max_used_device"], "/dev/nvme0n1p2")

    def test_mem(self) -> None:
        facts = parse_mem_sample(MEM_SAMPLE)
        self.assertEqual(facts["ram_used"], "15Gi")
        self.assertEqual(facts["ram_total"], "57Gi")
        self.assertEqual(facts["vram_used_mb"], 32607)
        self.assertEqual(facts["vram_total_mb"], 27048)


class TestLatestLine(unittest.TestCase):
    def test_returns_last_line(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as handle:
            handle.write("first\nsecond\n\n")
            path = handle.name
        try:
            self.assertEqual(latest_line(path), "second")
        finally:
            os.unlink(path)

    def test_missing_file(self) -> None:
        self.assertIsNone(latest_line("/no/such/file.log"))


class TestDeriveVerdict(unittest.TestCase):
    def base_facts(self) -> dict:
        return {
            "cpu": parse_cpu_sample(CPU_SAMPLE),
            "net": parse_net_sample(NET_SAMPLE),
            "disk": parse_disk_sample(DISK_SAMPLE),
            "mem": parse_mem_sample(MEM_SAMPLE),
            "lighthouse": {"nexus_ready": True, "online": ["gateway", "nexus"], "offline": []},
            "gpu": {"temp_c": 60.0, "power_w": 120.0},
        }

    def test_healthy_is_ok(self) -> None:
        facts = self.base_facts()
        facts["cpu"]["ram_free_pct"] = 55.0  # calm the busy sample
        facts["cpu"]["load1"] = 1.2
        facts["net"]["dns_rtt_ms"] = 27.0
        verdict, reasons = derive_verdict(facts)
        self.assertEqual(verdict, "ok")
        self.assertEqual(reasons, [])

    def test_disk_fail(self) -> None:
        facts = self.base_facts()
        facts["disk"]["max_used_pct"] = 96
        facts["disk"]["max_used_device"] = "/dev/nvme0n1p2"
        verdict, reasons = derive_verdict(facts)
        self.assertEqual(verdict, "fail")
        self.assertTrue(any("96%" in reason for reason in reasons))

    def test_nexus_not_ready_is_fail(self) -> None:
        facts = self.base_facts()
        facts["lighthouse"] = {"nexus_ready": False, "online": [], "offline": ["gateway", "nexus"]}
        verdict, _ = derive_verdict(facts)
        self.assertEqual(verdict, "fail")

    def test_missing_stores_warn(self) -> None:
        verdict, reasons = derive_verdict({})
        self.assertEqual(verdict, "warn")
        self.assertEqual(len(reasons), 5)

    def test_gpu_hot_warns(self) -> None:
        facts = self.base_facts()
        facts["gpu"] = {"temp_c": 88.0}
        verdict, reasons = derive_verdict(facts)
        self.assertEqual(verdict, "warn")
        self.assertTrue(any("88.0C" in reason for reason in reasons))


if __name__ == "__main__":
    unittest.main()
