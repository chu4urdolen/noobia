"""Unit tests for :func:`frame_quality`.

The tests exercise typical use cases: a completely dark frame, a mixed
distribution, a saturated frame, and a frame with an invalid length.
"""

import unittest
from projects.lynx_gain.frame_quality import frame_quality


class TestFrameQuality(unittest.TestCase):
    def test_all_zero(self):
        frame = bytes([0] * 16)
        res = frame_quality(frame, 4, 4)
        self.assertEqual(res["pixel_count"], 16)
        self.assertAlmostEqual(res["raw_mean"], 0.0)
        self.assertAlmostEqual(res["positive_mean"], 0.0)
        self.assertAlmostEqual(res["black_fraction"], 1.0)
        self.assertAlmostEqual(res["saturated_fraction"], 0.0)
        self.assertEqual(res["p50"], 0)
        self.assertEqual(res["p95"], 0)

    def test_mixed_values(self):
        # 8 values: 0,10,20,30,40,100,200,250
        frame = bytes([0,10,20,30,40,100,200,250,0,10,20,30,40,100,200,250])
        res = frame_quality(frame, 4, 4, black_level=16)
        self.assertEqual(res["pixel_count"], 16)
        # raw mean calculation
        expected_mean = sum(frame) / 16
        self.assertAlmostEqual(res["raw_mean"], expected_mean)
        # positive mean: values >16 are 20,30,40,100,200,250
        pos_vals = [v for v in frame if v > 16]
        pos_mean_expected = sum(v - 16 for v in pos_vals) / 16
        self.assertAlmostEqual(res["positive_mean"], pos_mean_expected)
        # black fraction: values <=16 are 0 and 10 (two of each)
        self.assertAlmostEqual(res["black_fraction"], 4/16)
        # saturated fraction: values >=250 are two 250s
        self.assertAlmostEqual(res["saturated_fraction"], 2/16)
        # percentiles: sorted values: [0,0,10,10,20,20,30,30,40,40,100,100,200,200,250,250]
        self.assertEqual(res["p50"], 30)
        self.assertEqual(res["p95"], 250)

    def test_all_saturated(self):
        frame = bytes([255] * 16)
        res = frame_quality(frame, 4, 4, black_level=16)
        self.assertAlmostEqual(res["positive_mean"], 239.0)  # 255-16
        self.assertAlmostEqual(res["saturated_fraction"], 1.0)

    def test_invalid_length(self):
        frame = bytes([0] * 15)
        with self.assertRaises(ValueError):
            frame_quality(frame, 4, 4)


if __name__ == "__main__":
    unittest.main()

