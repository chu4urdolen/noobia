"""Unit tests for :func:`geometry_for`.

The tests exercise normal operation for all supported sensors, error
conditions for unknown sensors, mismatched dimensions, invalid bytes per
pixel, and buffer over‑size.
"""

import unittest

from projects.lynx_gain.frame_geometry import geometry_for


class TestFrameGeometry(unittest.TestCase):
    def test_known_sensors(self):
        # sensor4 1600x1200
        res = geometry_for(4, 1600, 1200)
        self.assertEqual(res["image_bytes"], 1600 * 1200 * 1)
        self.assertEqual(res["allocation_bytes"], 1600 * 1200 * 1 + 24)

        # sensor0 4096x3072
        res = geometry_for(0, 4096, 3072)
        self.assertEqual(res["image_bytes"], 4096 * 3072)
        self.assertEqual(res["allocation_bytes"], 4096 * 3072 + 24)

        # sensor1 2320x1744
        res = geometry_for(1, 2320, 1744)
        self.assertEqual(res["image_bytes"], 2320 * 1744)
        self.assertEqual(res["allocation_bytes"], 2320 * 1744 + 24)

        # sensor2 3264x2448
        res = geometry_for(2, 3264, 2448)
        self.assertEqual(res["image_bytes"], 3264 * 2448)
        self.assertEqual(res["allocation_bytes"], 3264 * 2448 + 24)

    def test_bytes_per_pixel(self):
        # 2‑byte raw data
        res = geometry_for(4, 1600, 1200, bytes_per_pixel=2)
        self.assertEqual(res["image_bytes"], 1600 * 1200 * 2)
        self.assertEqual(res["allocation_bytes"], 1600 * 1200 * 2 + 24)

    def test_invalid_sensor(self):
        with self.assertRaises(ValueError):
            geometry_for(99, 100, 100)

    def test_mismatched_dimensions(self):
        with self.assertRaises(ValueError):
            geometry_for(4, 2000, 1200)

    def test_invalid_bpp(self):
        with self.assertRaises(ValueError):
            geometry_for(4, 1600, 1200, bytes_per_pixel=3)

    # The current sensor set and byte‑per‑pixel options never exceed 32 MiB.
    # This test is kept for documentation but no error is expected.
    def test_overflow_allocation(self):
        res = geometry_for(0, 4096, 3072, bytes_per_pixel=2)
        self.assertTrue(res["allocation_bytes"] <= 32 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()

