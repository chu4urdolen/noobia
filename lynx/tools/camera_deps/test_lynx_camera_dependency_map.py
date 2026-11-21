#!/usr/bin/env python3
"""Unit tests for the Lynx camera dependency and failure map."""

import unittest

from lynx_camera_dependency_map import (
    build_camera_dependency_map,
    verify_camera_gate_alignment,
    SENSOR_MAP,
)


class TestLynxCameraDependencyMap(unittest.TestCase):
    def test_all_four_sensors_present(self):
        dep_map = build_camera_dependency_map()
        sensors = dep_map["sensors"]
        self.assertEqual(set(sensors.keys()), {"GC02M1", "IMX355", "IMX890", "S5K3P9SP"})

    def test_sensor_roles_and_buses(self):
        self.assertEqual(SENSOR_MAP["GC02M1"].role, "rear_macro")
        self.assertEqual(SENSOR_MAP["GC02M1"].i2c_device, "9-003d")
        self.assertEqual(SENSOR_MAP["IMX355"].role, "rear_wide")
        self.assertEqual(SENSOR_MAP["IMX355"].i2c_device, "2-001a")
        self.assertEqual(SENSOR_MAP["IMX890"].role, "rear_main")
        self.assertEqual(SENSOR_MAP["IMX890"].i2c_device, "8-0036")
        self.assertEqual(SENSOR_MAP["S5K3P9SP"].role, "front")
        self.assertEqual(SENSOR_MAP["S5K3P9SP"].i2c_device, "9-0010")

    def test_proven_vs_four_cell_status(self):
        # Macro and Wide are single-cell Bayer with proven RAM ISP routes
        self.assertIn("Single-cell", SENSOR_MAP["GC02M1"].cfa_architecture)
        self.assertIn("Single-cell", SENSOR_MAP["IMX355"].cfa_architecture)
        self.assertEqual(SENSOR_MAP["GC02M1"].status_proven, "PROVEN_OPTICAL_RAM")
        self.assertEqual(SENSOR_MAP["IMX355"].status_proven, "PROVEN_FRAME_RAM")

        # Main and Front are four-cell Bayer and must be hard-refused
        self.assertIn("Four-cell", SENSOR_MAP["IMX890"].cfa_architecture)
        self.assertIn("Four-cell", SENSOR_MAP["S5K3P9SP"].cfa_architecture)
        self.assertEqual(SENSOR_MAP["IMX890"].status_proven, "UNTESTED_HARDWARE_REFUSED")
        self.assertEqual(SENSOR_MAP["S5K3P9SP"].status_proven, "UNTESTED_HARDWARE_REFUSED")
        self.assertEqual(SENSOR_MAP["IMX890"].gate_decision, "HARD_REFUSE")
        self.assertEqual(SENSOR_MAP["S5K3P9SP"].gate_decision, "HARD_REFUSE")

    def test_camera_gate_alignment(self):
        aligned, errs = verify_camera_gate_alignment()
        self.assertTrue(aligned, f"Failed alignment with lynx_camera_gate: {errs}")

    def test_next_smallest_offline_gate_defined(self):
        for name, spec in SENSOR_MAP.items():
            self.assertTrue(
                len(spec.next_smallest_offline_gate) > 10,
                f"Missing or brief offline gate for {name}",
            )
            self.assertTrue(
                len(spec.missing_evidence) >= 2,
                f"Missing evidence list should have multiple entries for {name}",
            )

    def test_source_citations_present(self):
        dep_map = build_camera_dependency_map()
        citations = dep_map["source_citations"]
        self.assertTrue(any("cust_mt6983_vitamin_camera_v4l2.dtsi" in c for c in citations))
        self.assertTrue(any("LYNX-CAMERA-PORT-PLAN.md" in c for c in citations))
        self.assertTrue(any("lynx_camera_gate.py" in c for c in citations))


if __name__ == "__main__":
    unittest.main()
