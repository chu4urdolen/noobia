#!/usr/bin/env python3
"""Unit tests for Lynx S5K3P9SP front camera bring-up preflight."""

import json
from pathlib import Path
import subprocess
import sys
import unittest

from lynx_s5k3p9sp_preflight import (
    evaluate_s5k3p9sp_preflight,
    validate_power_sequence,
    POWER_SEQUENCE_SPEC,
    REQUIRED_MODULES,
    EXPECTED_DPHY_LANES,
    EXPECTED_MCLK_MHZ,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


class TestLynxS5k3p9spPreflight(unittest.TestCase):
    def test_power_sequence_exact_specification(self):
        """Verify the 7-step power sequence matches the Nord 3 vendor driver."""
        self.assertEqual(len(POWER_SEQUENCE_SPEC), 7)
        self.assertEqual(POWER_SEQUENCE_SPEC[0]["id"], "HW_ID_MCLK")
        self.assertEqual(POWER_SEQUENCE_SPEC[0]["val"], 24)
        self.assertEqual(POWER_SEQUENCE_SPEC[1]["id"], "HW_ID_RST")
        self.assertEqual(POWER_SEQUENCE_SPEC[1]["val"], 0)
        self.assertEqual(POWER_SEQUENCE_SPEC[2]["id"], "HW_ID_DVDD")
        self.assertEqual(POWER_SEQUENCE_SPEC[2]["val"], 1104000)
        self.assertEqual(POWER_SEQUENCE_SPEC[3]["id"], "HW_ID_AVDD")
        self.assertEqual(POWER_SEQUENCE_SPEC[3]["val"], 2804000)
        self.assertEqual(POWER_SEQUENCE_SPEC[4]["id"], "HW_ID_DOVDD")
        self.assertEqual(POWER_SEQUENCE_SPEC[4]["val"], 1804000)
        self.assertEqual(POWER_SEQUENCE_SPEC[5]["id"], "HW_ID_MCLK_DRIVING_CURRENT")
        self.assertEqual(POWER_SEQUENCE_SPEC[5]["val"], 6)
        self.assertEqual(POWER_SEQUENCE_SPEC[6]["id"], "HW_ID_RST")
        self.assertEqual(POWER_SEQUENCE_SPEC[6]["val"], 1)

        ok, failures = validate_power_sequence(POWER_SEQUENCE_SPEC)
        self.assertTrue(ok)
        self.assertEqual(failures, [])

    def test_power_sequence_corrupted_step_rejected(self):
        corrupted = [dict(step) for step in POWER_SEQUENCE_SPEC]
        corrupted[2]["val"] = 1800000  # wrong DVDD voltage
        ok, failures = validate_power_sequence(corrupted)
        self.assertFalse(ok)
        self.assertIn("step_3_val_mismatch_1800000_vs_1104000", failures)

    def test_fixture_unbound_quiescent(self):
        path = FIXTURES_DIR / "s5k3p9sp-preflight-unbound.json"
        data = json.loads(path.read_text())
        verdict = evaluate_s5k3p9sp_preflight(data)

        self.assertTrue(verdict.is_valid)
        self.assertEqual(verdict.status, "UNBOUND_QUIESCENT")
        self.assertTrue(verdict.dt_node_mapped)
        self.assertTrue(verdict.dphy_lanes_mapped)
        self.assertTrue(verdict.power_sequence_mapped)
        self.assertTrue(verdict.mclk_mapped)
        self.assertTrue(verdict.vcm_absent_verified)
        self.assertFalse(verdict.modules_loaded)
        self.assertFalse(verdict.driver_bound)
        self.assertIn("quiescent state", verdict.summary)

    def test_fixture_bound_ready(self):
        path = FIXTURES_DIR / "s5k3p9sp-preflight-bound.json"
        data = json.loads(path.read_text())
        verdict = evaluate_s5k3p9sp_preflight(data)

        self.assertTrue(verdict.is_valid)
        self.assertEqual(verdict.status, "BOUND_READY")
        self.assertTrue(verdict.modules_loaded)
        self.assertTrue(verdict.driver_bound)
        self.assertIn("bound and operational", verdict.summary)

    def test_fixture_missing_dt_rejected(self):
        path = FIXTURES_DIR / "s5k3p9sp-preflight-missing-dt.json"
        data = json.loads(path.read_text())
        verdict = evaluate_s5k3p9sp_preflight(data)

        self.assertFalse(verdict.is_valid)
        self.assertEqual(verdict.status, "MALFORMED_SPEC")
        self.assertIn("missing_sensor1_node_in_dt", verdict.failures)
        self.assertIn("missing_s5k3p9sp_in_dt_sensor_names", verdict.failures)

    def test_hardware_specification_invariants(self):
        self.assertEqual(EXPECTED_DPHY_LANES, 4)
        self.assertEqual(EXPECTED_MCLK_MHZ, 24)
        self.assertEqual(len(REQUIRED_MODULES), 6)
        self.assertIn("imgsensor", REQUIRED_MODULES)
        self.assertIn("mtk_cam_isp", REQUIRED_MODULES)

    def test_cli_live_safety_gate(self):
        tool = Path(__file__).resolve().parent / "lynx_s5k3p9sp_preflight.py"
        res = subprocess.run([sys.executable, str(tool), "--live"], capture_output=True, text=True)
        self.assertEqual(res.returncode, 2)
        self.assertIn("Refusing live query without both --live and --allow-live", res.stderr)


if __name__ == "__main__":
    unittest.main()
