#!/usr/bin/env python3
"""Offline checks for passive Lynx USB mode classification."""

from pathlib import Path
import tempfile
import unittest

from lynx_presence import battery_alert, location, usb_probe


class PresenceTests(unittest.TestCase):
    def test_fastboot_requires_known_usb_identity_and_interface(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            device = root / "1-6"
            interface = root / "1-6:1.0"
            device.mkdir()
            interface.mkdir()
            (device / "idVendor").write_text("0e8d\n")
            (device / "idProduct").write_text("201c\n")
            for name, value in (("bInterfaceClass", "ff"),
                                ("bInterfaceSubClass", "42"),
                                ("bInterfaceProtocol", "03")):
                (interface / name).write_text(value + "\n")
            self.assertEqual(usb_probe(root), {"usb_present": True, "fastboot_usb": True})
            (interface / "bInterfaceProtocol").write_text("01\n")
            self.assertEqual(usb_probe(root), {"usb_present": True, "fastboot_usb": False})
            (device / "idProduct").write_text("ffff\n")
            self.assertEqual(usb_probe(root), {"usb_present": False, "fastboot_usb": False})

    def test_location_reports_positive_link_without_inferring_power(self):
        signals = {"usb_present": False, "fastboot_usb": False,
                   "wifi_ssh": False, "bluetooth_connected": False}
        self.assertEqual(location(signals), "not_observed")
        signals["bluetooth_connected"] = True
        self.assertEqual(location(signals), "bluetooth_connected")
        signals["wifi_ssh"] = True
        self.assertEqual(location(signals), "alpine_wifi")

    def test_battery_alert_respects_reserve_margin(self):
        self.assertEqual(battery_alert({"percent": 25}), "normal")
        self.assertEqual(battery_alert({"percent": 10}), "low")
        self.assertEqual(battery_alert({"percent": 5}), "critical")
        self.assertEqual(battery_alert(None), "unknown")


if __name__ == "__main__":
    unittest.main()
