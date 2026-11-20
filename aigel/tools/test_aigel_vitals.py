#!/usr/bin/env python3
"""Unit tests for Aigel's vitals board."""

import os
import subprocess
import tempfile
import unittest
from unittest import mock

from aigel_vitals import (
    derive_verdict,
    format_board,
    format_smart_disk,
    gpu_ecc,
    latest_line,
    live_ram_available,
    live_wifi_state,
    nvidia_xid_count,
    parse_cpu_sample,
    parse_disk_sample,
    parse_mem_sample,
    parse_net_sample,
    parse_smart_output,
    parse_smart_scan,
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
        # store format is "vram: {total}MiB / {used}MiB used"
        self.assertEqual(facts["vram_total_mb"], 32607)
        self.assertEqual(facts["vram_used_mb"], 27048)
        self.assertEqual(facts["ram_free"], "4.3Gi")


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


class TestFormatBoard(unittest.TestCase):
    def test_mem_line_uses_used_of_total_with_percent(self) -> None:
        facts = {"mem": parse_mem_sample(MEM_SAMPLE), "collected_at": "t"}
        board = format_board(facts, "ok", [])
        line = next(l for l in board.splitlines() if "mem   :" in l)
        self.assertIn("vram 27048/32607MiB used (83%)", line)
        self.assertIn("(4.3Gi free)", line)
        self.assertNotIn("free free", line)

    def test_gpu_line_shows_policy_and_flags_mismatch(self) -> None:
        facts = {
            "gpu": {"power_w": 400.7, "util_pct": 94.0, "temp_c": 68.0,
                    "vram_used_mb": 27048.0, "power_limit_w": 400.0, "file": "g.csv"},
            "policy": {"power_limit_w": 500},
            "collected_at": "t",
        }
        line = next(l for l in format_board(facts, "warn", []).splitlines() if "gpu   :" in l)
        self.assertIn("limit 400.0W policy 500W", line)
        self.assertIn("limit≠policy", line)

    def test_gpu_line_no_warning_when_policy_matches(self) -> None:
        facts = {
            "gpu": {"power_w": 480.0, "util_pct": 10.0, "temp_c": 50.0,
                    "vram_used_mb": 100.0, "power_limit_w": 500, "file": "g.csv"},
            "policy": {"power_limit_w": 500},
            "collected_at": "t",
        }
        line = next(l for l in format_board(facts, "ok", []).splitlines() if "gpu   :" in l)
        self.assertIn("limit 500W policy 500W", line)
        self.assertNotIn("limit≠policy", line)

    def test_quiet_board(self) -> None:
        self.assertIn("all quiet", format_board({"collected_at": "t"}, "ok", []))


NVME_SMART_OUTPUT = (
    "smartctl 7.5 2025-04-30\n"
    "=== START OF INFORMATION SECTION ===\n"
    "Model Number:                       Samsung SSD 980 2TB\n"
    "Serial Number:                      S0TESTSERIAL001\n"
    "=== START OF SMART DATA SECTION ===\n"
    "SMART overall-health self-assessment test result: PASSED\n"
    "SMART/Health Information (NVMe Log 0x02, NSID 0xffffffff)\n"
    "Critical Warning:                   0x00\n"
    "Temperature:                        42 Celsius\n"
    "Available Spare:                    100%\n"
    "Available Spare Threshold:          1%\n"
    "Percentage Used:                    0%\n"
    "Media and Data Integrity Errors:    0\n"
    "Error Information Log Entries:      0\n"
    "Temperature Sensor 1:               42 Celsius\n"
)
SATA_SMART_OUTPUT = (
    "Model Name: ST1000\n"
    "SMART overall-health self-assessment test result: PASSED\n"
    "ID# ATTRIBUTE_NAME          FLAG     VALUE WORST THRESH TYPE      UPDATED  WHEN_FAILED RAW_VALUE\n"
    "  5 Reallocated_Sector_Ct   0x0033   100   100   036    Pre-fail  Always       -       7\n"
    "187 Reported_Uncorrect     0x0032   200   200   000    Old_age   Always       -       0\n"
    "197 Current_Pending_Sector  0x0012   200   200   000    Old_age   Always       -       3\n"
    "194 Temperature_Celsius     0x0022   110   110   045    Old_age   Always       -       38\n"
)


class TestSmartParsing(unittest.TestCase):
    def test_scan_lists_devices_and_args(self) -> None:
        devices = parse_smart_scan(
            "/dev/nvme0 -d nvme # /dev/nvme0, NVMe device\n/dev/sda # bare\n\n"
        )
        self.assertEqual(devices, [("/dev/nvme0", ["-d", "nvme"]), ("/dev/sda", [])])

    def test_nvme_facts(self) -> None:
        facts = parse_smart_output(NVME_SMART_OUTPUT)
        self.assertEqual(facts["model"], "Samsung SSD 980 2TB")
        self.assertEqual(facts["health"], "PASSED")
        self.assertEqual(facts["temp_c"], 42)
        self.assertEqual(facts["nvme_available_spare_pct"], 100)
        self.assertEqual(facts["nvme_percentage_used_pct"], 0)
        self.assertEqual(facts["media_errors"], 0)
        self.assertEqual(facts["error_log_entries"], 0)
        # NVMe does not expose SATA realloc/pending attrs — honest n/a, not zero
        self.assertNotIn("reallocated", facts)
        self.assertNotIn("pending", facts)

    def test_sata_attribute_table(self) -> None:
        facts = parse_smart_output(SATA_SMART_OUTPUT)
        self.assertEqual(facts["health"], "PASSED")
        self.assertEqual(facts["reallocated"], 7)
        self.assertEqual(facts["pending"], 3)
        self.assertEqual(facts["temp_c"], 38)

    def test_format_smart_disk_line(self) -> None:
        line = format_smart_disk({
            "device": "/dev/nvme0", "model": "Samsung SSD 980 2TB",
            "health": "PASSED", "temp_c": 42, "media_errors": 0,
            "nvme_available_spare_pct": 100, "nvme_percentage_used_pct": 0,
        })
        self.assertIn("health=PASSED", line)
        self.assertIn("realloc=n/a pending=n/a", line)
        self.assertIn("spare=100%", line)
        self.assertIn("used=0%", line)


class TestLiveReaders(unittest.TestCase):
    @staticmethod
    def fake_proc(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")

    def test_wifi_up(self) -> None:
        with mock.patch(
            "aigel_vitals.subprocess.run",
            return_value=self.fake_proc(
                "4: wlx40a5ef5f66f1: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc fq_codel state UP\n"
            ),
        ):
            self.assertEqual(live_wifi_state(), "UP")

    def test_wifi_down(self) -> None:
        with mock.patch(
            "aigel_vitals.subprocess.run",
            return_value=self.fake_proc(
                "4: wlx40a5ef5f66f1: <BROADCAST,MULTICAST> mtu 1500 state DOWN\n"
            ),
        ):
            self.assertEqual(live_wifi_state(), "DOWN")

    def test_wifi_lower_up_is_not_up_alone(self) -> None:
        # LOWER_UP without the bare UP flag must still count as down
        with mock.patch(
            "aigel_vitals.subprocess.run",
            return_value=self.fake_proc(
                "4: wlx40a5ef5f66f1: <BROADCAST,MULTICAST,LOWER_UP> mtu 1500 state DOWN\n"
            ),
        ):
            self.assertEqual(live_wifi_state(), "DOWN")

    def test_wifi_binary_missing(self) -> None:
        with mock.patch("aigel_vitals.subprocess.run", side_effect=OSError):
            self.assertIsNone(live_wifi_state())

    def test_ram_available_from_meminfo(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".meminfo", delete=False) as handle:
            handle.write(
                "MemTotal:       60553456 kB\nMemFree:         4028664 kB\n"
                "MemAvailable:   46077804 kB\n"
            )
            path = handle.name
        try:
            facts = live_ram_available(path)
            self.assertEqual(facts["available_kb"], 46077804)
            self.assertAlmostEqual(facts["available_pct"], 76.1)
        finally:
            os.unlink(path)

    def test_ram_missing_memavailable(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".meminfo", delete=False) as handle:
            handle.write("MemTotal: 100 kB\n")
            path = handle.name
        try:
            self.assertIsNone(live_ram_available(path))
        finally:
            os.unlink(path)

    def test_gpu_ecc_na_is_honest_not_zero(self) -> None:
        output = (
            "    ECC Errors\n"
            "        Volatile\n"
            "            Correctable : N/A\n"
            "            Uncorrectable : N/A\n"
            "        Aggregate\n"
            "            Correctable : N/A\n"
            "            Uncorrectable : N/A\n"
        )
        with mock.patch("aigel_vitals.subprocess.run", return_value=self.fake_proc(output)):
            facts = gpu_ecc()
        self.assertFalse(facts["available"])
        self.assertIsNone(facts["correctable"])
        self.assertIsNone(facts["uncorrectable"])

    def test_gpu_ecc_aggregate_counts(self) -> None:
        output = (
            "    ECC Errors\n"
            "        Aggregate\n"
            "            Correctable : 12\n"
            "            Uncorrectable : 3\n"
        )
        with mock.patch("aigel_vitals.subprocess.run", return_value=self.fake_proc(output)):
            facts = gpu_ecc()
        self.assertTrue(facts["available"])
        self.assertEqual(facts["correctable"], 12)
        self.assertEqual(facts["uncorrectable"], 3)

    def test_xid_counts_only_nvrm_pattern(self) -> None:
        journal = (
            "Nov 18 16:31:02 nexus kernel: "
            "r8169 0000:22:00.0 eth0: RTL8168h/8111h, 02:00:00:00:00:05, XID 541, IRQ 61\n"
            "Nov 18 16:31:05 nexus kernel: NVRM: Xid (PCI:0000:10:00): 31, Channel 0x00000004\n"
        )
        with mock.patch("aigel_vitals.subprocess.run", return_value=self.fake_proc(journal)):
            self.assertEqual(nvidia_xid_count(), 1)

    def test_xid_zero_when_only_the_r8169_false_friend(self) -> None:
        journal = (
            "Nov 18 16:31:02 nexus kernel: "
            "r8169 0000:22:00.0 eth0: RTL8168h/8111h, 02:00:00:00:00:05, XID 541, IRQ 61\n"
        )
        with mock.patch("aigel_vitals.subprocess.run", return_value=self.fake_proc(journal)):
            self.assertEqual(nvidia_xid_count(), 0)


class TestDeriveVerdictLive(unittest.TestCase):
    def base_facts(self) -> dict:
        return {
            "cpu": parse_cpu_sample(CPU_SAMPLE),
            "net": parse_net_sample(NET_SAMPLE),
            "disk": parse_disk_sample(DISK_SAMPLE),
            "mem": parse_mem_sample(MEM_SAMPLE),
            "gpu": {"temp_c": 50.0},
            "ram_live": {"available_pct": 76.1},
        }

    def test_live_wifi_up_overrides_stale_store_down(self) -> None:
        facts = self.base_facts()
        facts["net"] = {"wifi_state": "DOWN"}
        facts["wifi_live"] = {"state": "UP"}
        verdict, reasons = derive_verdict(facts)
        self.assertEqual(verdict, "ok")
        self.assertFalse(any("Wi-Fi" in reason for reason in reasons))

    def test_live_wifi_down_fails_even_if_store_says_up(self) -> None:
        facts = self.base_facts()
        facts["wifi_live"] = {"state": "DOWN"}
        verdict, reasons = derive_verdict(facts)
        self.assertEqual(verdict, "fail")
        self.assertTrue(any("DOWN (live)" in reason for reason in reasons))

    def test_ram_live_available_calms_stale_free_sample(self) -> None:
        # the store sample's MemFree share is low; live MemAvailable says fine
        facts = self.base_facts()
        verdict, reasons = derive_verdict(facts)
        self.assertFalse(any("ram" in reason for reason in reasons))

    def test_smart_failed_health_is_fail(self) -> None:
        facts = self.base_facts()
        facts["smart"] = {"available": True, "disks": [
            {"device": "/dev/sda", "health": "FAILED", "model": "ST1000"},
        ]}
        verdict, reasons = derive_verdict(facts)
        self.assertEqual(verdict, "fail")
        self.assertTrue(any("SMART overall-health FAILED on /dev/sda" in r for r in reasons))

    def test_smart_pending_sectors_is_fail(self) -> None:
        facts = self.base_facts()
        facts["smart"] = {"available": True, "disks": [
            {"device": "/dev/sdb", "health": "PASSED", "pending": 3},
        ]}
        verdict, reasons = derive_verdict(facts)
        self.assertEqual(verdict, "fail")
        self.assertTrue(any("pending sectors: 3 on /dev/sdb" in r for r in reasons))

    def test_nvme_without_realloc_attrs_is_quiet(self) -> None:
        facts = self.base_facts()
        facts["smart"] = {"available": True, "disks": [
            {"device": "/dev/nvme0", "health": "PASSED", "media_errors": 0},
        ]}
        verdict, reasons = derive_verdict(facts)
        self.assertEqual(verdict, "ok")
        self.assertEqual(reasons, [])

    def test_xid_events_warn(self) -> None:
        facts = self.base_facts()
        facts["gpu_longevity"] = {"xid_count": 3}
        verdict, reasons = derive_verdict(facts)
        self.assertEqual(verdict, "warn")
        self.assertTrue(any("3 NVIDIA Xid" in reason for reason in reasons))

    def test_limit_policy_mismatch_warns(self) -> None:
        facts = self.base_facts()
        facts["gpu"] = {"temp_c": 50.0, "power_limit_w": 400.0}
        facts["policy"] = {"power_limit_w": 500}
        verdict, reasons = derive_verdict(facts)
        self.assertEqual(verdict, "warn")
        self.assertTrue(any("differs from policy" in reason for reason in reasons))

    def test_live_limit_matching_policy_is_quiet(self) -> None:
        facts = self.base_facts()
        facts["gpu"] = {"temp_c": 50.0, "power_limit_w": 400.0}  # stale store
        facts["policy"] = {"power_limit_w": 500}
        facts["gpu_longevity"] = {"power_limit_w_live": 500.0}
        verdict, reasons = derive_verdict(facts)
        self.assertFalse(any("policy" in reason for reason in reasons))

    def test_ecc_uncorrectable_fails_and_correctable_warns(self) -> None:
        facts = self.base_facts()
        facts["gpu_longevity"] = {"ecc": {"available": True, "correctable": 5, "uncorrectable": 2}}
        verdict, reasons = derive_verdict(facts)
        self.assertEqual(verdict, "fail")
        self.assertTrue(any("uncorrectable" in reason for reason in reasons)
                        and any("correctable" in reason for reason in reasons))

    def test_ecc_unavailable_is_quiet(self) -> None:
        facts = self.base_facts()
        facts["gpu_longevity"] = {"ecc": {"available": False, "correctable": None, "uncorrectable": None}}
        verdict, reasons = derive_verdict(facts)
        self.assertEqual(verdict, "ok")
        self.assertEqual(reasons, [])


class TestFormatBoardLive(unittest.TestCase):
    def test_net_line_shows_live_and_stale_store(self) -> None:
        facts = {
            "net": {"wifi_state": "DOWN", "dns_rtt_ms": 34.2},
            "wifi_live": {"state": "UP"},
            "collected_at": "t",
        }
        line = next(l for l in format_board(facts, "ok", []).splitlines() if "net   :" in l)
        self.assertIn("live=UP", line)
        self.assertIn("store said DOWN", line)

    def test_net_line_agreement_has_no_stale_note(self) -> None:
        facts = {
            "net": {"wifi_state": "UP", "dns_rtt_ms": 34.2},
            "wifi_live": {"state": "UP"},
            "collected_at": "t",
        }
        line = next(l for l in format_board(facts, "ok", []).splitlines() if "net   :" in l)
        self.assertIn("live=UP", line)
        self.assertNotIn("stale", line)

    def test_mem_line_shows_mem_available(self) -> None:
        facts = {
            "mem": parse_mem_sample(MEM_SAMPLE),
            "ram_live": {"available_pct": 77.6},
            "collected_at": "t",
        }
        line = next(l for l in format_board(facts, "ok", []).splitlines() if "mem   :" in l)
        self.assertIn("MemAvailable 77.6% (live)", line)

    def test_gpu_line_live_limit_ecc_na_and_xid(self) -> None:
        facts = {
            "gpu": {"power_w": 10.0, "util_pct": 1.0, "temp_c": 40.0,
                    "vram_used_mb": 100.0, "power_limit_w": 400.0, "file": "g.csv"},
            "policy": {"power_limit_w": 500},
            "gpu_longevity": {
                "power_limit_w_live": 500.0,
                "ecc": {"available": False, "correctable": None, "uncorrectable": None},
                "xid_count": 0,
            },
            "collected_at": "t",
        }
        line = next(l for l in format_board(facts, "ok", []).splitlines() if "gpu   :" in l)
        self.assertIn("limit 500.0W policy 500W", line)
        self.assertNotIn("limit≠policy", line)
        self.assertIn("ecc n/a (not available on this card)", line)
        self.assertIn("xid 0 (since boot)", line)

    def test_smart_lines(self) -> None:
        facts = {
            "smart": {"available": True, "disks": [
                {"device": "/dev/nvme0", "model": "Samsung SSD 980 2TB", "health": "PASSED",
                 "temp_c": 42, "media_errors": 0,
                 "nvme_available_spare_pct": 100, "nvme_percentage_used_pct": 0},
            ]},
            "collected_at": "t",
        }
        line = next(l for l in format_board(facts, "ok", []).splitlines() if "smart :" in l)
        self.assertIn("health=PASSED", line)
        self.assertIn("spare=100%", line)

    def test_smart_unavailable_line(self) -> None:
        facts = {"smart": {"available": False, "reason": "smartctl not available or unreadable"},
                 "collected_at": "t"}
        self.assertIn("smartctl not available", format_board(facts, "ok", []))


if __name__ == "__main__":
    unittest.main()
