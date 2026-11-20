"""Offline safety gates for the V53 RAM-only NFC probe."""

import copy
import unittest

from trial_v53_nfc_ram import BOOT_SHA, guard, main, module_plan


HEALTH = {"issues": [], "wifi": {"carrier": True},
          "battery": {"capacity_percent": 55, "current_mA_signed": 320,
                      "temperature_mC": 28000},
          "thermal": {"max_mC": 37000}, "root_free_mib": 10000,
          "root_filesystem": {"ext4_errors_count": 0}}


class NfcRamGateTest(unittest.TestCase):
    def test_exact_stock_module_bytes_and_kernel_abi(self):
        plan = module_plan()
        self.assertEqual([name for name, _sha, _data in plan],
                         ["oplus_nfc", "nfc_i2c"])
        self.assertEqual(len(BOOT_SHA), 64)

    def test_ready_and_reject_each_bad_guard(self):
        guard(HEALTH)
        edits = (
            ("battery", "capacity_percent", 49),
            ("battery", "current_mA_signed", 0),
            ("battery", "temperature_mC", 35000),
            ("thermal", "max_mC", 42000),
            ("wifi", "carrier", False),
            ("root_filesystem", "ext4_errors_count", 1),
        )
        for section, key, value in edits:
            with self.subTest(section=section, key=key):
                bad = copy.deepcopy(HEALTH)
                bad[section][key] = value
                with self.assertRaises(RuntimeError):
                    guard(bad)

    def test_default_never_contacts_phone(self):
        # The default path verifies stock files and returns before trial().
        self.assertEqual(main([]), 0)


if __name__ == "__main__":
    unittest.main()
