"""Offline checks for the V53 GNSS trial's image and evidence gates."""

import unittest

import build_v53_precal_settle as build
import lynx_boot_a_v53_trial as image
import stage_august_gnss_bundle as bundle
import trial_v52_gnss_link as link
import trial_v52_gnss_mnld as mnld
import trial_v52_gps_pwr as power
import trial_v52_gps_scp_stack as scp


class TestGnssV53Candidate(unittest.TestCase):
    def test_all_stages_pin_the_verified_images(self):
        for stage in (bundle, link, mnld, power, scp):
            with self.subTest(stage=stage.__name__):
                self.assertEqual(stage.BOOT_SHAS["v52"], build.V52_SHA)
                self.assertEqual(stage.BOOT_SHAS["v53"], image.V53_SHA)

    def test_v53_requires_completed_sustained_bluetooth_receipt(self):
        receipt = {
            "state": "stopped-after-healthy-trial",
            "watchdog_mode": "stop-only",
            "nexus": {"state": "reconnect-smoke-complete"},
            "steps": ([{"name": f"health_sample_{i}", "exit": 0}
                       for i in range(30)] +
                      [{"name": name, "exit": 0}
                       for name in ("stop", "stopped_check", "cancel_watchdog")]),
        }
        self.assertTrue(link.valid_bt_receipt(receipt, "v53"))
        receipt["steps"][0]["exit"] = 1
        self.assertFalse(link.valid_bt_receipt(receipt, "v53"))
        receipt["steps"][0]["exit"] = 0
        receipt["steps"] = receipt["steps"][1:]
        self.assertFalse(link.valid_bt_receipt(receipt, "v53"))

    def test_v52_receipt_gate_is_preserved(self):
        receipt = {"state": "hci-commands-complete-healthy",
                   "watchdog_cancelled": True}
        self.assertTrue(link.valid_bt_receipt(receipt, "v52"))
        receipt["watchdog_cancelled"] = False
        self.assertFalse(link.valid_bt_receipt(receipt, "v52"))


if __name__ == "__main__":
    unittest.main()
