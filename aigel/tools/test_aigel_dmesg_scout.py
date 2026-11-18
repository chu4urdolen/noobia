#!/usr/bin/env python3
"""Unit tests for Aigel's dmesg scout."""

import unittest

from aigel_dmesg_scout import build_digest, classify_lines, line_timestamp, read_kernel_log


FIXTURE = [
    "2026-11-18T00:10:01+02:00 Nexus kernel: system boot",
    "2026-11-18T00:12:11+02:00 Nexus kernel: NVRM: Xid (GPU:05:00:00): 31, Channel 00000008",
    "2026-11-18T00:12:12+02:00 Nexus kernel: NVRM: Xid (GPU:05:00:00): 31, Channel 00000008",
    "2026-11-18T00:15:30+02:00 Nexus kernel: Out of memory: Killed process 4242 (stress-ng)",
    "2026-11-18T00:20:00+02:00 Nexus kernel: e1000e: NIC Link is Up 1000 Mbps",
    "2026-11-18T00:21:00+02:00 Nexus kernel: EXT4-fs error (dev nvme0n1p2): ext4_reserve_metadata_write_blocks",
    "2026-11-18T00:22:00+02:00 Nexus kernel: CPU0: Core temperature above threshold, throttling",
    "2026-11-18T00:23:00+02:00 Nexus kernel: usb 1-3: USB disconnect, device number 7",
    "2026-11-18T00:24:00+02:00 Nexus kernel: EDAC mc0: 1 CE memory read error on CPU0",
    "2026-11-18T00:25:00+02:00 Nexus kernel: everything is fine",
    "2026-11-18T00:26:00+02:00 Nexus kernel: failed to allocate slab",
]


from aigel_dmesg_scout import parse_since


class TestParseSince(unittest.TestCase):
    def test_relative_hours(self) -> None:
        self.assertEqual(parse_since("2h ago"), (None, 7200))

    def test_relative_minutes_no_ago(self) -> None:
        self.assertEqual(parse_since("30m"), (None, 1800))

    def test_relative_days(self) -> None:
        self.assertEqual(parse_since("1d"), (None, 86400))

    def test_relative_seconds(self) -> None:
        self.assertEqual(parse_since("45s ago"), (None, 45))

    def test_absolute_passthrough(self) -> None:
        self.assertEqual(parse_since("2026-11-18 02:00"), ("2026-11-18 02:00", None))

    def test_empty_and_none(self) -> None:
        self.assertEqual(parse_since(None), (None, None))
        self.assertEqual(parse_since(""), (None, None))


class TestClassifyLines(unittest.TestCase):
    def setUp(self) -> None:
        self.classified = classify_lines(FIXTURE)

    def test_categories_found(self) -> None:
        self.assertEqual(
            set(self.classified),
            {"gpu", "oom_kill", "nic_link", "storage", "thermal", "usb", "hardware", "general"},
        )

    def test_first_match_wins(self) -> None:
        self.assertIn("2026-11-18T00:12:11+02:00 Nexus kernel: NVRM: Xid (GPU:05:00:00): 31, Channel 00000008",
                      [item["line"] for item in self.classified["gpu"]])

    def test_oom(self) -> None:
        self.assertEqual(len(self.classified["oom_kill"]), 1)

    def test_benign_line_dropped(self) -> None:
        for items in self.classified.values():
            for item in items:
                self.assertNotIn("everything is fine", item["line"])

    def test_general_bucket(self) -> None:
        self.assertEqual([item["line"] for item in self.classified["general"]],
                         ["2026-11-18T00:26:00+02:00 Nexus kernel: failed to allocate slab"])

    def test_benign_boot_chatter_ignored(self) -> None:
        lines = [
            "kern: thermal_sys: Registered thermal governor 'fair_share'",
            "kern: nvidia: loading out-of-tree module taints kernel.",
            "kern: r8169 eth0: RTL8168h, XID 541, IRQ 61",
            "kern: ACPI: [Firmware Bug]: BIOS _OSI(Linux) query ignored",
        ]
        self.assertEqual(classify_lines(lines), {})


class TestBuildDigest(unittest.TestCase):
    def test_dedup_repeats(self) -> None:
        digest = build_digest(classify_lines(FIXTURE), limit=5)
        gpu_examples = digest["gpu"]["examples"]
        self.assertEqual(gpu_examples[0]["count"], 2)
        self.assertEqual(digest["gpu"]["count"], 2)

    def test_limit_applied(self) -> None:
        digest = build_digest(classify_lines(FIXTURE), limit=1)
        for entry in digest.values():
            self.assertLessEqual(len(entry["examples"]), 1)

    def test_index_span(self) -> None:
        digest = build_digest(classify_lines(FIXTURE), limit=5)
        self.assertEqual(digest["gpu"]["first_index"], 1)
        self.assertEqual(digest["gpu"]["last_index"], 2)


class TestLineTimestamp(unittest.TestCase):
    def test_short_iso(self) -> None:
        self.assertEqual(line_timestamp("2026-11-18T00:12:11+02:00 kernel: x"),
                         "2026-11-18T00:12:11+02:00")

    def test_dmesg_relative(self) -> None:
        self.assertEqual(line_timestamp("[    12.345678] kernel: x"), "boot+12.345678s")

    def test_none(self) -> None:
        self.assertIsNone(line_timestamp("no timestamp here"))


class TestReadKernelLog(unittest.TestCase):
    def test_explicit_bad_source(self) -> None:
        lines, backend = read_kernel_log("dmesg", timeout=5)
        self.assertIsNone(backend if not lines else "unexpected-failure",
                          "dmesg should either return lines or fail cleanly")


if __name__ == "__main__":
    unittest.main()
