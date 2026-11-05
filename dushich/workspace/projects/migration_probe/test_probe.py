"""Unit tests for the ``migration_probe`` module.

The tests exercise :func:`migration_probe.double` with a variety of
integers, ensuring it behaves correctly for positive, zero, and negative
values.
"""

import unittest

from projects.migration_probe import double


class TestDouble(unittest.TestCase):
    def test_positive(self):
        self.assertEqual(double(1), 2)
        self.assertEqual(double(5), 10)

    def test_zero(self):
        self.assertEqual(double(0), 0)

    def test_negative(self):
        self.assertEqual(double(-1), -2)
        self.assertEqual(double(-10), -20)


if __name__ == "__main__":
    unittest.main()

