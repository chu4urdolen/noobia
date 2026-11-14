"""Unit tests for :mod:`projects.banshee_bridge_probe.hello`.

The test simply verifies that the :func:`banner` function returns the
expected greeting string.
"""

import unittest

from projects.banshee_bridge_probe.hello import banner


class TestBanner(unittest.TestCase):
    def test_hello(self):
        self.assertEqual(banner("World"), "Hello, World!")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

