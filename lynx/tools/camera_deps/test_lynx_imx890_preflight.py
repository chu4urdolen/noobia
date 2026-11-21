#!/usr/bin/env python3
"""Unit tests for Lynx IMX890 main camera bring-up preflight."""

import json
from pathlib import Path
import subprocess
import sys
import unittest

from lynx_imx890_preflight import (
    evaluate_imx890_preflight,
    validate_power_sequence,
    POWER_SEQUENCE_SPEC,
    REQUIRED_MODULES,
    EXPECTED_CPHY_TRIOS,
    EXPECTED_MCLK_MHZ,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


class TestLynxImx890Preflight(unittest.TestCase):
    def test_power_sequence_exact_specification(self):
        """Verify the 9-step power sequence matches the Nord 3 vendor driver."""
        self.assertEqual(len(POWER_SEQUENCE_SPEC), 9)
        self.assertEqual(POWER_SEQUENCE_SPEC[0]["id"], "HW_ID_MCLK")
        self.assertEqual(POWER_SEQUENCE_SPEC[0]["val"], 24)
        self.assertEqual(POWER_SEQUENCE_SPEC[1]["id"], "HW_ID_RST")
        self.assertEqual(POWER_SEQUENCE_SPEC[1]["val"], 0)
        self.assertEqual(POWER_SEQUENCE_SPEC[2]["id"], "HW_ID_AVDD")
        self.assertEqual(POWER_SEQUENCE_SPEC[2]["val"], 2804000)
        self.assertEqual(POWER_SEQUENCE_SPEC[3]["id"], "HW_ID_AVDD1")
        self.assertEqual(POWER_SEQUENCE_SPEC[3]["val"], 1804000)
        self.assertEqual(POWER_SEQUENCE_SPEC[4]["id"], "HW_ID_AFVDD")
        self.assertEqual(POWER_SEQUENCE_SPEC[4]["val"], 2804000)
        self.assertEqual(POWER_SEQUENCE_SPEC[5]["id"], "HW_ID_DVDD")
        self.assertEqual(POWER_SEQUENCE_SPEC[5]["val"], 1)
        self.assertEqual(POWER_SEQUENCE_SPEC[6]["id"], "HW_ID_DOVDD")
        self.assertEqual(POWER_SEQUENCE_SPEC[6]["val"], 1804000)
        self.assertEqual(POWER_SEQUENCE_SPEC[7]["id"], "HW_ID_MCLK_DRIVING_CURRENT")
        self.assertEqual(POWER_SEQUENCE_SPEC[7]["val"], 4)
        self.assertEqual(POWER_SEQUENCE_SPEC[8]["id"], "HW_ID_RST")
        self.assertEqual(POWER_SEQUENCE_SPEC[8]["val"], 1)

        ok, failures = validate_power_sequence(POWER_SEQUENCE_SPEC)
        self.assertTrue(ok)
        self.assertEqual(failures, [])

    def test_power_sequence_corrupted_step_rejected(self):
        corrupted = [dict(step) for step in POWER_SEQUENCE_SPEC]
        corrupted[2]["val"] = 1800000  # wrong AVDD voltage
        ok, failures = validate_power_sequence(corrupted)
        self.assertFalse(ok)
        self.assertIn("step_3_val_mismatch_1800000_vs_2804000", failures)

    def test_fixture_unbound_quiescent(self):
        path = FIXTURES_DIR / "imx890-preflight-unbound.json"
        data = json.loads(path.read_text())
        verdict = evaluate_imx890_preflight(data)

        self.assertTrue(verdict.is_valid)
        self.assertEqual(verdict.status, "UNBOUND_QUIESCENT")
        self.assertTrue(verdict.dt_node_mapped)
        self.assertTrue(verdict.cphy_lanes_mapped)
        self.assertTrue(verdict.power_sequence_mapped)
        self.assertTrue(verdict.mclk_mapped)
        self.assertTrue(verdict.vcm_mapped)
        self.assertFalse(verdict.modules_loaded)
        self.assertFalse(verdict.driver_bound)
        self.assertIn("quiescent state", verdict.summary)

    def test_fixture_bound_ready(self):
        path = FIXTURES_DIR / "imx890-preflight-bound.json"
        data = json.loads(path.read_text())
        verdict = evaluate_imx890_preflight(data)

        self.assertTrue(verdict.is_valid)
        self.assertEqual(verdict.status, "BOUND_READY")
        self.assertTrue(verdict.modules_loaded)
        self.assertTrue(verdict.driver_bound)
        self.assertIn("bound and operational", verdict.summary)

    def test_fixture_missing_dt_rejected(self):
        path = FIXTURES_DIR / "imx890-preflight-missing-dt.json"
        data = json.loads(path.read_text())
        verdict = evaluate_imx890_preflight(data)

        self.assertFalse(verdict.is_valid)
        self.assertEqual(verdict.status, "MALFORMED_SPEC")
        self.assertIn("missing_sensor0_node_in_dt", verdict.failures)
        self.assertIn("missing_imx890_in_dt_sensor_names", verdict.failures)

    def test_hardware_specification_invariants(self):
        self.assertEqual(EXPECTED_CPHY_TRIOS, 3)
        self.assertEqual(EXPECTED_MCLK_MHZ, 24)
        self.assertEqual(len(REQUIRED_MODULES), 6)
        self.assertIn("imgsensor", REQUIRED_MODULES)
        self.assertIn("mtk_cam_isp", REQUIRED_MODULES)

    def test_cli_live_safety_gate(self):
        tool = Path(__file__).resolve().parent / "lynx_imx890_preflight.py"
        res = subprocess.run([sys.executable, str(tool), "--live"], capture_output=True, text=True)
        self.assertEqual(res.returncode, 2)
        self.assertIn("Refusing live query without both --live and --allow-live", res.stderr)


if __name__ == "__main__":
    unittest.main()
