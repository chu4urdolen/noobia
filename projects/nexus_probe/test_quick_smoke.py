"""Unit tests for the quick smoke helper.

The test simply verifies that the :func:`add` function from
``quick_smoke`` behaves as expected for a basic integer addition.
"""

import unittest
from projects.nexus_probe.quick_smoke import add


class TestQuickSmoke(unittest.TestCase):
    def test_addition(self):
        self.assertEqual(add(2, 3), 5)


if __name__ == "__main__":
    unittest.main()

