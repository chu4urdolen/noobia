#!/usr/bin/env python3
"""Offline unit tests for Lynx fingerprint inventory and secure boundary evaluator."""

import unittest

from lynx_fingerprint_inventory import (
    PINNED_V53_BOOT_ID,
    evaluate_fingerprint_inventory,
)


class TestFingerprintInventory(unittest.TestCase):
    def test_baseline_v53_alpine_inventory(self):
        # Baseline: DT present, SPI bus present, driver not loaded, no TEE daemon, no HAL
        obs = {
            "phone": {
                "boot_id": PINNED_V53_BOOT_ID,
                "device_tree": {
                    "present": True,
                    "compatible": "oplus,fp_spi",
                    "path": "/sys/firmware/devicetree/base/spi7@11017000/fingerprint@0",
                },
                "spi_bus": {
                    "present": True,
                    "device_node": "/sys/bus/spi/devices/spi7.0",
                    "driver_bound": False,
                    "driver_name": None,
                },
                "modules": ["spi_mt65xx", "olc", "mtk_disp_notify", "oplus_bsp_tp_notify"],
                "devices": {
                    "fingerprint_dev": False,
                    "mobicore_dev": False,
                },
                "daemons": ["lynx-health", "lynx-wifi"],
            }
        }
        res = evaluate_fingerprint_inventory(obs)
        self.assertEqual(res["verdict"], "hardware_present_driver_missing")
        self.assertTrue(res["layers"]["hardware"]["present"])
        self.assertEqual(res["layers"]["kernel_driver"]["state"], "missing_driver")
        self.assertEqual(res["layers"]["tee_boundary"]["state"], "tee_driver_missing")
        self.assertEqual(res["layers"]["userspace"]["state"], "hal_absent")
        self.assertTrue(res["boot_id_matches_pinned"])
        self.assertIn("uff_fp_driver is not loaded", res["gaps"][0])

    def test_driver_loaded_unbound(self):
        obs = {
            "phone": {
                "boot_id": PINNED_V53_BOOT_ID,
                "device_tree": {"present": True, "compatible": "oplus,fp_spi"},
                "spi_bus": {"present": True, "driver_bound": False},
                "modules": ["spi_mt65xx", "uff_fp_driver"],
                "devices": {"fingerprint_dev": False, "mobicore_dev": False},
                "daemons": [],
            }
        }
        res = evaluate_fingerprint_inventory(obs)
        self.assertEqual(res["layers"]["kernel_driver"]["state"], "driver_loaded_unbound")
        self.assertTrue(any("failed to bind" in g for g in res["gaps"]))

    def test_driver_bound_tee_missing(self):
        obs = {
            "phone": {
                "boot_id": PINNED_V53_BOOT_ID,
                "device_tree": {"present": True, "compatible": "oplus,fp_spi"},
                "spi_bus": {"present": True, "driver_bound": True, "driver_name": "fp_spi_driver"},
                "modules": ["spi_mt65xx", "uff_fp_driver", "oplus_fp_common"],
                "devices": {"fingerprint_dev": True, "mobicore_dev": False},
                "daemons": [],
            }
        }
        res = evaluate_fingerprint_inventory(obs)
        self.assertEqual(res["verdict"], "hardware_present_driver_bound")
        self.assertEqual(res["layers"]["kernel_driver"]["state"], "driver_bound")
        self.assertEqual(res["layers"]["tee_boundary"]["state"], "tee_driver_missing")
        self.assertEqual(res["layers"]["userspace"]["state"], "char_dev_present_hal_absent")

    def test_complete_stack_mock(self):
        obs = {
            "phone": {
                "boot_id": PINNED_V53_BOOT_ID,
                "device_tree": {"present": True, "compatible": "oplus,fp_spi"},
                "spi_bus": {"present": True, "driver_bound": True, "driver_name": "fp_spi_driver"},
                "modules": ["spi_mt65xx", "uff_fp_driver", "mcDrvModule"],
                "devices": {"fingerprint_dev": True, "mobicore_dev": True},
                "daemons": ["mcDriverDaemon", "vendor.oplus.hardware.biometrics.fingerprint"],
            }
        }
        res = evaluate_fingerprint_inventory(obs)
        self.assertEqual(res["verdict"], "biometrics_stack_complete")
        self.assertEqual(res["layers"]["tee_boundary"]["state"], "tee_ready")
        self.assertEqual(res["layers"]["userspace"]["state"], "hal_running")

    def test_hardware_missing(self):
        obs = {
            "phone": {
                "boot_id": PINNED_V53_BOOT_ID,
                "device_tree": {"present": False},
                "spi_bus": {"present": False},
                "modules": [],
                "devices": {},
                "daemons": [],
            }
        }
        res = evaluate_fingerprint_inventory(obs)
        self.assertEqual(res["verdict"], "hardware_missing")
        self.assertFalse(res["layers"]["hardware"]["present"])

    def test_stale_boot(self):
        obs = {
            "phone": {
                "boot_id": "other-boot-id",
                "device_tree": {"present": True, "compatible": "oplus,fp_spi"},
                "spi_bus": {"present": True},
                "modules": ["spi_mt65xx"],
                "devices": {},
                "daemons": [],
            }
        }
        res = evaluate_fingerprint_inventory(obs)
        self.assertEqual(res["verdict"], "stale_boot")
        self.assertFalse(res["boot_id_matches_pinned"])

    def test_timeout_and_error(self):
        res1 = evaluate_fingerprint_inventory({"timeout": True, "error": "timed out"})
        self.assertEqual(res1["verdict"], "timeout")

        res2 = evaluate_fingerprint_inventory({"error": "ssh connect fail"})
        self.assertEqual(res2["verdict"], "error")


if __name__ == "__main__":
    unittest.main()
