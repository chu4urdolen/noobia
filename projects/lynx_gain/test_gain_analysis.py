import unittest
from projects.lynx_gain.gain_analysis import gain_mapper

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

if __name__ == "__main__":
    unittest.main()
