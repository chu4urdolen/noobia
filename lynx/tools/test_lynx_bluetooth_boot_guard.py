#!/usr/bin/env python3
"""Offline safety checks for Bluetooth boot-order admission."""

import unittest

from lynx_bluetoothd import radio_boot_order


def staged(station=47.84):
    return "\n".join((
        "LYNX_WIFI uptime=17.76 CHECKPOINT_MODULE_OK wlan_drv_gen4m_6983.ko",
        "LYNX_WIFI uptime=17.77 CHECKPOINT_MODULE_OK btif_drv.ko",
        "LYNX_WIFI uptime=17.78 CHECKPOINT_MODULE_OK bt_drv_6983.ko",
        f"LYNX_WIFI uptime={station:.2f} WIFI_STAGE WIFI_STATION_POWER_ON",
    ))


class BootOrderTests(unittest.TestCase):
    def test_accepts_settled_registration(self):
        self.assertTrue(radio_boot_order(staged()))

    def test_rejects_calibration_overlap(self):
        self.assertFalse(radio_boot_order(staged(station=18.00)))

    def test_rejects_missing_or_duplicate_stage(self):
        good = staged()
        self.assertFalse(radio_boot_order(good.replace("CHECKPOINT_MODULE_OK bt_drv_6983.ko",
                                                     "CHECKPOINT_MODULE_FAILED bt_drv_6983.ko")))
        self.assertFalse(radio_boot_order(good + "\n" + good.splitlines()[2]))

    def test_rejects_bluetooth_after_wifi(self):
        self.assertFalse(radio_boot_order(staged().replace(
            "uptime=17.78 CHECKPOINT_MODULE_OK bt_drv_6983.ko",
            "uptime=50.00 CHECKPOINT_MODULE_OK bt_drv_6983.ko")))


if __name__ == "__main__":
    unittest.main()
