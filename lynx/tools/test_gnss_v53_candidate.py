"""Offline checks for the V53 GNSS trial's image and evidence gates."""

import unittest

import build_v53_precal_settle as build
import lynx_gnss_sandbox_runner as sandbox
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

    def test_v53_boot_stack_reuse_only_loads_missing_tail(self):
        reused, pending = scp.load_plan("v53", True)
        self.assertEqual(reused, scp.ORDER[:6])
        self.assertEqual(pending, ("connscp", "gps_scp"))
        self.assertEqual(scp.load_plan("v52", False), ((), scp.ORDER))
        with self.assertRaises(ValueError):
            scp.load_plan("v52", True)

    def test_v53_node_guard_matches_observed_same_boot_nodes(self):
        self.assertEqual(sandbox.NODE_MAJORS["v53"], {
            "gpsdl0": 493, "gpsdl1": 493, "gps_emi": 492,
            "gps_pwr": 491, "gps2scp": 489,
        })


if __name__ == "__main__":
    unittest.main()
