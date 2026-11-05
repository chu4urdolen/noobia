import unittest
from projects.lynx_gain.gain_analysis import gain_mapper, pack_stagger_ae
import struct

class TestGainMapper(unittest.TestCase):
    def test_endpoints(self):
        # Lower endpoint
        self.assertEqual(gain_mapper(64), 1024)
        # Upper endpoint
        self.assertEqual(gain_mapper(768), 12288)

    def test_middle(self):
        # Middle of the range: (64+768)//2 = 416
        self.assertEqual(gain_mapper(416), 6656)

    def test_invalid_low(self):
        with self.assertRaises(ValueError):
            gain_mapper(63)

    def test_invalid_high(self):
        with self.assertRaises(ValueError):
            gain_mapper(769)

    def test_monotonicity(self):
        prev = None
        for val in range(64, 769):
            cur = gain_mapper(val)
            if prev is not None:
                self.assertGreater(cur, prev, f"Non‑monotonic at {val}")
            prev = cur


class TestPackStaggerAE(unittest.TestCase):
    def test_valid_values(self):
        # Use the lower bound values for exposure and gain
        data = pack_stagger_ae(1005, 1024)
        self.assertEqual(len(data), 52)
        # Unpack and verify first 13 values
        values = struct.unpack("<13I", data)
        self.assertEqual(values[0], 1005)  # exposure
        self.assertEqual(values[5], 1024)  # gain
        # all other values should be zero
        for i in range(1, 5):
            self.assertEqual(values[i], 0)
        for i in range(6, 13):
            self.assertEqual(values[i], 0)

    def test_invalid_exposure(self):
        with self.assertRaises(ValueError):
            pack_stagger_ae(1004, 1024)

    def test_invalid_gain(self):
        with self.assertRaises(ValueError):
            pack_stagger_ae(1005, 1023)

    def test_non_int(self):
        with self.assertRaises(ValueError):
            pack_stagger_ae("1005", 1024)
        with self.assertRaises(ValueError):
            pack_stagger_ae(1005, 1024.0)

if __name__ == "__main__":
    unittest.main()
