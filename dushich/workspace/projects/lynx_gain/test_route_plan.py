"""Tests for :func:`plan_route`.
"""

import unittest

from projects.lynx_gain.route_plan import plan_route


class TestRoutePlan(unittest.TestCase):
    def test_4_to_2(self):
        expected = [
            "[27]1:0",  # seninf-1:1 disable
            "[45]0:0",  # sensor4:0 disable
            "[71]0:5",  # sensor2:0 enable
            "[53]1:5",  # seninf-2:1 enable
            "[615]0:5",  # CAMSV-0 enable
        ]
        self.assertEqual(plan_route(4, 2), expected)

    def test_2_to_4(self):
        expected = [
            "[615]0:0",  # CAMSV-0 disable
            "[53]1:0",  # seninf-2:1 disable
            "[71]0:0",  # sensor2:0 disable
            "[45]0:5",  # sensor4:0 enable
            "[27]1:5",  # seninf-1:1 enable
        ]
        self.assertEqual(plan_route(2, 4), expected)

    def test_same_sensor(self):
        with self.assertRaises(ValueError):
            plan_route(4, 4)

    def test_invalid_sensor(self):
        with self.assertRaises(ValueError):
            plan_route(3, 4)

    def test_invalid_target(self):
        with self.assertRaises(ValueError):
            plan_route(4, 5)


if __name__ == "__main__":
    unittest.main()

