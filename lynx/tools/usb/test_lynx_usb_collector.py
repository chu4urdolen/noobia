#!/usr/bin/env python3
"""Offline unit tests for Lynx USB ACM continuity and acceptance collector."""

import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from lynx_usb_collector import (
    PINNED_V53_BOOT_ID,
    evaluate_usb_link,
    collect_nexus_usb_state,
)


class TestLynxUSBCollector(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def test_connected_link(self):
        obs = {
            "phone": {
                "boot_id": PINNED_V53_BOOT_ID,
                "udcs": ["11201000.usb0", "dummy_udc.0"],
                "mtu3_mode": "3",
                "ttygs_present": True,
                "gadget_bound": True,
            },
            "nexus": {
                "ttyacm_present": True,
                "device_node": "/dev/ttyACM0",
                "vendor_id": "1d6b",
                "product_id": "0104",
                "serial": "LYNX001",
                "product_name": "Lynx_Nord_3",
                "driver": "cdc_acm",
            },
        }
        res = evaluate_usb_link(obs)
        self.assertEqual(res["verdict"], "connected")
        self.assertTrue(res["continuity"]["both_endpoints_active"])
        self.assertEqual(res["continuity"]["link_state"], "active_bidirectional_candidate")
        self.assertTrue(res["phone_gadget"]["active"])
        self.assertTrue(res["nexus_host"]["active"])

    def test_disconnected_link(self):
        obs = {
            "phone": {
                "boot_id": PINNED_V53_BOOT_ID,
                "udcs": ["dummy_udc.0"],
                "mtu3_mode": "1",
                "ttygs_present": False,
                "gadget_bound": False,
            },
            "nexus": {
                "ttyacm_present": False,
                "device_node": None,
                "vendor_id": None,
                "product_id": None,
                "driver": None,
            },
        }
        res = evaluate_usb_link(obs)
        self.assertEqual(res["verdict"], "disconnected")
        self.assertFalse(res["continuity"]["both_endpoints_active"])
        self.assertEqual(res["continuity"]["link_state"], "disconnected")
        self.assertFalse(res["phone_gadget"]["active"])
        self.assertFalse(res["nexus_host"]["active"])

    def test_partial_phone_only(self):
        # Phone gadget is up in mode 3, but cable is unplugged so Nexus sees nothing
        obs = {
            "phone": {
                "boot_id": PINNED_V53_BOOT_ID,
                "udcs": ["11201000.usb0"],
                "mtu3_mode": "3",
                "ttygs_present": True,
                "gadget_bound": True,
            },
            "nexus": {
                "ttyacm_present": False,
                "device_node": None,
                "vendor_id": None,
                "product_id": None,
                "driver": None,
            },
        }
        res = evaluate_usb_link(obs)
        self.assertEqual(res["verdict"], "partial")
        self.assertFalse(res["continuity"]["both_endpoints_active"])
        self.assertEqual(res["continuity"]["link_state"], "phone_only")
        self.assertTrue(res["phone_gadget"]["active"])
        self.assertFalse(res["nexus_host"]["active"])

    def test_partial_nexus_only(self):
        # Nexus still has lingering /dev/ttyACM0 or host device, but phone MTU3 fell back to mode 1
        obs = {
            "phone": {
                "boot_id": PINNED_V53_BOOT_ID,
                "udcs": ["11201000.usb0"],
                "mtu3_mode": "1",  # dual-role auto, not peripheral
                "ttygs_present": False,
                "gadget_bound": False,
            },
            "nexus": {
                "ttyacm_present": True,
                "device_node": "/dev/ttyACM0",
                "vendor_id": "1d6b",
                "product_id": "0104",
                "driver": "cdc_acm",
            },
        }
        res = evaluate_usb_link(obs)
        self.assertEqual(res["verdict"], "partial")
        self.assertFalse(res["continuity"]["both_endpoints_active"])
        self.assertEqual(res["continuity"]["link_state"], "nexus_only")
        self.assertFalse(res["phone_gadget"]["active"])
        self.assertTrue(res["nexus_host"]["active"])

    def test_stale_boot_id(self):
        # Boot ID differs from pinned V53 foothold
        obs = {
            "phone": {
                "boot_id": "deadbeef-1234-5678-9abc-def012345678",
                "udcs": ["11201000.usb0"],
                "mtu3_mode": "3",
                "ttygs_present": True,
                "gadget_bound": True,
            },
            "nexus": {
                "ttyacm_present": True,
                "device_node": "/dev/ttyACM0",
                "vendor_id": "1d6b",
                "product_id": "0104",
                "driver": "cdc_acm",
            },
        }
        res = evaluate_usb_link(obs)
        self.assertEqual(res["verdict"], "stale_boot")
        self.assertFalse(res["continuity"]["both_endpoints_active"])
        self.assertEqual(res["continuity"]["link_state"], "stale_boot")
        self.assertFalse(res["phone_gadget"]["boot_id_matches_pinned"])

    def test_timeout_handling(self):
        obs = {
            "timeout": True,
            "error": "SSH command timed out after 8s",
        }
        res = evaluate_usb_link(obs)
        self.assertEqual(res["verdict"], "timeout")
        self.assertFalse(res["continuity"]["both_endpoints_active"])
        self.assertIn("timed out", res["reasons"][0])

    def test_collection_error_handling(self):
        obs = {
            "collection_error": "Connection refused",
        }
        res = evaluate_usb_link(obs)
        self.assertEqual(res["verdict"], "error")
        self.assertFalse(res["continuity"]["both_endpoints_active"])
        self.assertIn("Connection refused", res["reasons"][0])

    def test_empty_observation(self):
        res = evaluate_usb_link({})
        self.assertEqual(res["verdict"], "disconnected")
        self.assertFalse(res["continuity"]["both_endpoints_active"])


if __name__ == "__main__":
    unittest.main()
