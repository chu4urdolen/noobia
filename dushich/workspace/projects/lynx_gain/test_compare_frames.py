"""Tests for :mod:`compare_frames`.

The tests use small synthetic byte arrays to exercise the various
behaviours:

* **Signal ratio** – a 2×2 image where the second frame is half the first
  should yield a ratio of 2.
* **Unchanged frame** – identical frames should produce a diff grid of all
  zeros and a signal ratio of ``None``.
* **Invalid length** – buffers that are too short raise :class:`ValueError`.
"""

import json
import unittest
from pathlib import Path

from compare_frames import compare_frames


class TestCompareFrames(unittest.TestCase):
    def setUp(self) -> None:
        self.width = 8
        self.height = 8
        self.black_level = 16

    def test_signal_ratio(self):
        # Frame 1: all pixels 100
        first = bytes([100] * (self.width * self.height))
        # Frame 2: all pixels 50
        second = bytes([50] * (self.width * self.height))
        result = compare_frames(first, second, self.width, self.height, self.black_level)
        # raw means
        self.assertAlmostEqual(result["raw_mean1"], 100.0)
        self.assertAlmostEqual(result["raw_mean2"], 50.0)
        # signal means (after subtracting 16)
        self.assertAlmostEqual(result["signal_mean1"], 84.0)
        self.assertAlmostEqual(result["signal_mean2"], 34.0)
        # ratio
        self.assertAlmostEqual(result["signal_ratio"], 84.0 / 34.0)
        # diff grid should be non‑zero mean differences
        for row in result["diff_grid"]:
            for val in row:
                self.assertNotEqual(val, 0)

    def test_unchanged_frame(self):
        data = bytes([120] * (self.width * self.height))
        result = compare_frames(data, data, self.width, self.height, self.black_level)
        # When both signals are identical and non‑zero the ratio should be 1.0
        self.assertAlmostEqual(result["signal_ratio"], 1.0)
        # diff grid all zeros
        for row in result["diff_grid"]:
            for val in row:
                self.assertAlmostEqual(val, 0.0)

    def test_invalid_length(self):
        first = bytes([0] * (self.width * self.height - 1))
        second = bytes([0] * (self.width * self.height))
        with self.assertRaises(ValueError):
            compare_frames(first, second, self.width, self.height, self.black_level)


if __name__ == "__main__":
    unittest.main()

