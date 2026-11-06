"""Unit tests for :func:`make_lut`.

The tests cover

* default parameters (identity mapping with black level 16, gain 1, gamma 1).
* clipping at the black level – values below the offset map to zero.
* amplification – a gain >1 stretches the range.
* invalid parameter values raise :class:`ValueError` or :class:`TypeError`.
"""

import unittest
from projects.lynx_gain.preview_lut import make_lut


class TestMakeLUT(unittest.TestCase):
    def test_identity_default(self):
        lut = make_lut()
        # With black_level=16, gain=1, gamma=1 the mapping is simple
        for v in range(256):
            # values below 16 map to 0
            expected = 0 if v < 16 else v - 16
            self.assertEqual(lut[v], expected)

    def test_black_clipping(self):
        lut = make_lut(black_level=200)
        for v in range(256):
            expected = 0 if v <= 200 else v - 200
            self.assertEqual(lut[v], expected)

    def test_gain_amplification(self):
        lut = make_lut(gain=2.0)
        # values below the black level remain 0
        for v in range(16):
            self.assertEqual(lut[v], 0)
        # pick a value above the black level; e.g. 20 -> (4)*2 = 8
        self.assertEqual(lut[20], 8)
        # a larger value, e.g. 128 -> (112)*2 = 224
        self.assertEqual(lut[128], 224)

    def test_invalid_params(self):
        with self.assertRaises(ValueError):
            make_lut(black_level=-1)
        with self.assertRaises(ValueError):
            make_lut(black_level=255)
        with self.assertRaises(ValueError):
            make_lut(gain=0)
        with self.assertRaises(ValueError):
            make_lut(gamma=0)
        with self.assertRaises(TypeError):
            make_lut(black_level="16")


if __name__ == "__main__":
    unittest.main()

