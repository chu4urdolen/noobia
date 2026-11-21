#!/usr/bin/env python3
"""Offline unit tests for Lynx NFC tag-exchange readiness validator."""

import json
from pathlib import Path
import unittest

from lynx_nfc_validator import (
    PINNED_V53_BOOT_ID,
    evaluate_nfc_readiness,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class TestNFCValidator(unittest.TestCase):
    def test_real_v53_probe_receipt(self):
        fixture_path = FIXTURES / "v53-nfc-probe-receipt.json"
        with open(fixture_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        res = evaluate_nfc_readiness(data)
        # Should verify driver probe, but classify tag exchange as pending
        self.assertEqual(res["verdict"], "driver_verified_tag_pending")
        self.assertTrue(res["driver_probe"]["verified"])
        self.assertTrue(res["driver_probe"]["driver_bound"])
        self.assertTrue(res["driver_probe"]["nq_node_present"])
        self.assertTrue(res["driver_probe"]["watchdog_cancelled"])
        self.assertFalse(res["tag_exchange"]["verified"])
        self.assertIn("GET_VERSION passed", res["reasons"][0])
        self.assertIn("physical RF tag exchange has not been executed", res["reasons"][0])

    def test_tag_exchange_success_receipt(self):
        receipt = {
            "state": "probe-complete-healthy",
            "boot_id": PINNED_V53_BOOT_ID,
            "loaded": ["oplus_nfc", "nfc_i2c"],
            "driver_bound": True,
            "nq_node": True,
            "watchdog_armed": True,
            "watchdog_cancelled": True,
            "tag_exchange": {
                "tag_detected": True,
                "tag_uid": "04A1B2C3D4E5F6",
                "rf_carrier_active": True,
            },
        }
        res = evaluate_nfc_readiness(receipt)
        self.assertEqual(res["verdict"], "tag_exchange_verified")
        self.assertTrue(res["tag_exchange"]["verified"])
        self.assertEqual(res["tag_exchange"]["tag_uid"], "04A1B2C3D4E5F6")

    def test_stale_boot_id(self):
        receipt = {
            "state": "probe-complete-healthy",
            "boot_id": "different-boot-id",
            "loaded": ["oplus_nfc", "nfc_i2c"],
            "driver_bound": True,
            "nq_node": True,
            "watchdog_armed": True,
            "watchdog_cancelled": True,
        }
        res = evaluate_nfc_readiness(receipt)
        self.assertEqual(res["verdict"], "stale_boot")
        self.assertFalse(res["boot_id_matches_pinned"])

    def test_missing_module_or_node(self):
        receipt = {
            "state": "probe-incomplete",
            "boot_id": PINNED_V53_BOOT_ID,
            "loaded": ["oplus_nfc"],  # missing nfc_i2c
            "driver_bound": False,
            "nq_node": False,
            "watchdog_armed": True,
            "watchdog_cancelled": True,
        }
        res = evaluate_nfc_readiness(receipt)
        self.assertEqual(res["verdict"], "probe_failed")
        self.assertFalse(res["driver_probe"]["verified"])

    def test_watchdog_unconfirmed_cancelled(self):
        receipt = {
            "state": "probe-complete-healthy",
            "boot_id": PINNED_V53_BOOT_ID,
            "loaded": ["oplus_nfc", "nfc_i2c"],
            "driver_bound": True,
            "nq_node": True,
            "watchdog_armed": True,
            "watchdog_cancelled": False,  # watchdog was not confirmed cancelled
        }
        res = evaluate_nfc_readiness(receipt)
        self.assertEqual(res["verdict"], "probe_failed")
        self.assertFalse(res["driver_probe"]["verified"])


if __name__ == "__main__":
    unittest.main()
