import unittest
from pathlib import Path

from camera_route_plan import plan_route
from switch_camera_camsv_route import detect_route


class RoutePlanTest(unittest.TestCase):
    def test_switch_to_wide_disconnects_macro_first(self):
        self.assertEqual(plan_route(4, 2), [
            "27:1->615:0[4]", "45:0->27:0[4]",
            "71:0->53:0[5]", "53:1->615:0[5]",
        ])

    def test_return_to_macro_disconnects_wide_first(self):
        self.assertEqual(plan_route(2, 4), [
            "53:1->615:0[4]", "71:0->53:0[4]",
            "45:0->27:0[5]", "27:1->615:0[5]",
        ])

    def test_same_route_is_rejected(self):
        with self.assertRaises(ValueError):
            plan_route(4, 4)

    def test_saved_live_graphs_select_exactly_one_route(self):
        root = Path(__file__).resolve().parent.parent
        macro = (root / "logs/camera-graph-20261105-v53-live.txt").read_text()
        wide = (root / "logs/camera-route-switch-1793897872599657409/graph_after.txt").read_text()
        self.assertEqual(detect_route(macro), 4)
        self.assertEqual(detect_route(wide), 2)
