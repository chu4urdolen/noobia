"""Offline safety gates for the V53 RAM-only USB mtu3 probe."""

import copy
import unittest

from trial_v53_usb_ram import BOOT_SHA, guard, main, module_plan

HEALTH = {
    "issues": [],
    "wifi": {"carrier": True},
    "battery": {
        "capacity_percent": 100,
        "current_mA_signed": 0,
        "temperature_mC": 29000,
    },
    "thermal": {"max_mC": 38000},
    "root_free_mib": 10000,
    "root_filesystem": {"ext4_errors_count": 0},
}


class UsbRamGateTest(unittest.TestCase):
    def test_exact_stock_module_bytes_and_kernel_abi(self):
        plan = module_plan()
        self.assertEqual([name for name, _sha, _data in plan], ["mtu3"])
        self.assertEqual(len(BOOT_SHA), 64)

    def test_ready_and_reject_each_bad_guard(self):
        guard(HEALTH)
        edits = (
            ("battery", "capacity_percent", 49),
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

    def test_safe_power_charging_or_full(self):
        # Discharging below 100% is rejected
        bad = copy.deepcopy(HEALTH)
        bad["battery"]["capacity_percent"] = 80
        bad["battery"]["current_mA_signed"] = -150
        with self.assertRaises(RuntimeError):
            guard(bad)

        # Charging (> 0 mA) is accepted
        charging = copy.deepcopy(HEALTH)
        charging["battery"]["capacity_percent"] = 80
        charging["battery"]["current_mA_signed"] = 300
        guard(charging)

    def test_default_never_contacts_phone(self):
        self.assertEqual(main([]), 0)


if __name__ == "__main__":
    unittest.main()
