"""Unit tests for the offline Lynx camera gate."""

import json
import unittest

from lynx_camera_gate import (
    ALLOW,
    ALLOWED_ROUTES,
    DECISIONS,
    REFUSE,
    REFUSED_SENSORS,
    evaluate_request,
    gate,
)


def request(**overrides):
    """Build a valid baseline request, then apply test overrides."""
    base = {
        "sensor": "GC02M1",
        "width": 1600,
        "height": 1200,
        "pixel_format": "BA81",
        "optically_verified": True,
    }
    base.update(overrides)
    return base


class DecisionShapeTests(unittest.TestCase):
    def test_decision_shape_is_stable(self):
        decision = gate(request())
        self.assertIn(decision.decision, DECISIONS)
        self.assertIsInstance(decision.reason, str)
        self.assertTrue(decision.reason)
        d = decision.as_dict()
        self.assertEqual(d["decision"], decision.decision)
        self.assertEqual(d["allowed"], decision.decision == ALLOW)
        self.assertEqual(d["reason"], decision.reason)
        self.assertTrue({"sensor", "width", "height", "pixel_format",
                         "optically_verified"} <= set(d))


class AllowedRouteTests(unittest.TestCase):
    def test_verified_macro_gc02m1_is_allowed(self):
        decision = gate(request())
        self.assertEqual(decision.decision, ALLOW)
        self.assertEqual(decision.sensor, "GC02M1")
        self.assertIn("GC02M1", decision.reason)

    def test_verified_wide_imx355_is_allowed(self):
        decision = gate(request(
            sensor="IMX355", width=3264, height=2448, pixel_format="BA81"))
        self.assertEqual(decision.decision, ALLOW)
        self.assertIn("IMX355", decision.reason)

    def test_matching_is_case_and_whitespace_insensitive(self):
        decision = gate(request(sensor="  gc02m1 ", pixel_format="ba81"))
        self.assertEqual(decision.decision, ALLOW)
        self.assertEqual(decision.sensor, "GC02M1")
        self.assertEqual(decision.pixel_format, "BA81")

    def test_allow_reason_is_tied_to_the_route(self):
        for (sensor, width, height, pixel_format), reason in ALLOWED_ROUTES.items():
            decision = gate(request(sensor=sensor, width=width,
                                    height=height, pixel_format=pixel_format))
            self.assertEqual(decision.decision, ALLOW)
            self.assertEqual(decision.reason, reason)


class RefusedSensorTests(unittest.TestCase):
    def test_imx890_is_refused_as_untested(self):
        decision = gate(request(sensor="IMX890", width=4000, height=3000))
        self.assertEqual(decision.decision, REFUSE)
        self.assertIn("IMX890", decision.reason)
        self.assertIn("four-cell", decision.reason)

    def test_s5k3p9sp_is_refused_as_untested(self):
        decision = gate(request(sensor="S5K3P9SP", width=4032, height=3024))
        self.assertEqual(decision.decision, REFUSE)
        self.assertIn("S5K3P9SP", decision.reason)

    def test_refused_sensor_wins_even_when_verified_and_known_format(self):
        # IMX890 with the exact verified macro geometry/format is still refused
        # because the sensor itself is a hard block.
        decision = gate(request(sensor="IMX890", width=1600, height=1200,
                                pixel_format="BA81", optically_verified=True))
        self.assertEqual(decision.decision, REFUSE)
        self.assertIn("IMX890", decision.reason)

    def test_all_refused_sensors_are_declared(self):
        self.assertEqual(
            frozenset(REFUSED_SENSORS),
            frozenset({"IMX890", "S5K3P9SP"}),
        )


class NotVerifiedTests(unittest.TestCase):
    def test_macro_without_optical_verification_is_refused(self):
        decision = gate(request(optically_verified=False))
        self.assertEqual(decision.decision, REFUSE)
        self.assertIn("optically_verified", decision.reason)

    def test_wide_without_optical_verification_is_refused(self):
        decision = gate(request(
            sensor="IMX355", width=3264, height=2448,
            optically_verified=False))
        self.assertEqual(decision.decision, REFUSE)
        self.assertIn("optically_verified", decision.reason)


class UnknownRouteTests(unittest.TestCase):
    def test_known_sensor_with_wrong_geometry_is_refused(self):
        decision = gate(request(width=1920, height=1080))
        self.assertEqual(decision.decision, REFUSE)
        self.assertIn("route", decision.reason)

    def test_known_sensor_with_wrong_format_is_refused(self):
        decision = gate(request(pixel_format="YUV420"))
        self.assertEqual(decision.decision, REFUSE)
        self.assertIn("route", decision.reason)

    def test_imx355_at_macro_geometry_is_refused(self):
        decision = gate(request(
            sensor="IMX355", width=1600, height=1200, pixel_format="BA81"))
        self.assertEqual(decision.decision, REFUSE)

    def test_unknown_sensor_is_refused(self):
        decision = gate(request(sensor="OV5640"))
        self.assertEqual(decision.decision, REFUSE)
        self.assertIn("allow list", decision.reason)


class MalformedRequestTests(unittest.TestCase):
    def test_missing_field_is_refused(self):
        bad = request()
        del bad["sensor"]
        decision = evaluate_request(bad)
        self.assertEqual(decision.decision, REFUSE)
        self.assertIn("sensor", decision.reason)

    def test_non_object_json_is_refused(self):
        decision = gate("[1, 2, 3]")
        self.assertEqual(decision.decision, REFUSE)
        self.assertIn("JSON object", decision.reason)

    def test_invalid_json_is_refused_not_raised(self):
        decision = gate("{not valid json")
        self.assertEqual(decision.decision, REFUSE)
        self.assertIn("JSON", decision.reason)

    def test_width_must_be_a_plain_integer(self):
        for bad_width in ("1600", 1600.0, True, None):
            decision = evaluate_request(request(width=bad_width))
            self.assertEqual(decision.decision, REFUSE, bad_width)
            self.assertIn("width", decision.reason)

    def test_nonpositive_dimension_is_refused(self):
        for bad in ({"width": 0}, {"height": -1}):
            decision = evaluate_request(request(**bad))
            self.assertEqual(decision.decision, REFUSE)

    def test_optically_verified_must_be_a_boolean(self):
        decision = evaluate_request(request(optically_verified="yes"))
        self.assertEqual(decision.decision, REFUSE)
        self.assertIn("optically_verified", decision.reason)

    def test_non_mapping_request_is_refused(self):
        decision = evaluate_request(["sensor"])
        self.assertEqual(decision.decision, REFUSE)
        self.assertIn("mapping", decision.reason)

    def test_bytes_json_is_accepted(self):
        raw = json.dumps(request()).encode("utf-8")
        decision = gate(raw)
        self.assertEqual(decision.decision, ALLOW)


if __name__ == "__main__":
    unittest.main()
