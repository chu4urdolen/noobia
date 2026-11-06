"""Unit tests for :func:`roi_bayer_means`.

The tests exercise both the BGGR and RGGB phase logic, verify mean
calculations on a small synthetic 4×4 frame, and check that the function
raises :class:`ValueError` for invalid input such as odd coordinates,
out‑of‑bounds ROI, or unsupported phase values.
"""

import unittest
from projects.lynx_gain.roi_channels import roi_bayer_means


class TestRoiBayerMeans(unittest.TestCase):
    """Test channel statistics for a synthetic 4×4 Bayer image."""

    @staticmethod
    def _synthetic_frame() -> bytes:
        """Return a 4×4 frame with values 10..160.

        The layout is row‑major: 10,20,30,40, 50,60,70,80, 90,100,110,120,
        130,140,150,160.
        """
        return bytes([
            10, 20, 30, 40,
            50, 60, 70, 80,
            90,100,110,120,
            130,140,150,160,
        ])

    def test_bggr_full_roi(self):
        frame = self._synthetic_frame()
        means = roi_bayer_means(frame, 4, 4, 0, 0, 4, 4, phase="bggr")
        self.assertAlmostEqual(means["B"], 60.0)
        self.assertAlmostEqual(means["G1"], 70.0)
        # For a 4x4 BGGR image the G2 pixels are 50, 70, 130, 150
        # mean = 100
        self.assertAlmostEqual(means["G2"], 100.0)
        self.assertAlmostEqual(means["R"], 110.0)

    def test_rggb_full_roi(self):
        frame = self._synthetic_frame()
        means = roi_bayer_means(frame, 4, 4, 0, 0, 4, 4, phase="rggb")
        self.assertAlmostEqual(means["R"], 60.0)
        self.assertAlmostEqual(means["G1"], 70.0)
        # In RGGB, G2 positions are the same as in BGGR
        self.assertAlmostEqual(means["G2"], 100.0)
        self.assertAlmostEqual(means["B"], 110.0)

    def test_invalid_phase(self):
        frame = self._synthetic_frame()
        with self.assertRaises(ValueError):
            roi_bayer_means(frame, 4, 4, 0, 0, 4, 4, phase="invalid")

    def test_odd_coordinates(self):
        frame = self._synthetic_frame()
        # x0 odd
        with self.assertRaises(ValueError):
            roi_bayer_means(frame, 4, 4, 1, 0, 4, 4)
        # y1 odd
        with self.assertRaises(ValueError):
            roi_bayer_means(frame, 4, 4, 0, 0, 4, 3)

    def test_out_of_bounds(self):
        frame = self._synthetic_frame()
        with self.assertRaises(ValueError):
            roi_bayer_means(frame, 4, 4, 0, 0, 5, 4)
        with self.assertRaises(ValueError):
            roi_bayer_means(frame, 4, 4, 0, 0, 4, 5)

    def test_partial_roi(self):
        frame = self._synthetic_frame()
        # Top‑left 2×2 block
        means = roi_bayer_means(frame, 4, 4, 0, 0, 2, 2, phase="bggr")
        # Pixels: 10,20,50,60 => B=10, G1=20, G2=50, R=60
        self.assertAlmostEqual(means["B"], 10.0)
        self.assertAlmostEqual(means["G1"], 20.0)
        self.assertAlmostEqual(means["G2"], 50.0)
        self.assertAlmostEqual(means["R"], 60.0)


if __name__ == "__main__":
    unittest.main()

