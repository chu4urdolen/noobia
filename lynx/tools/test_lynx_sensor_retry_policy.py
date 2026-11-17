"""Unit tests for the Lynx sensorhub/audio bootstrap retry policy."""

import unittest

from lynx_sensor_retry_policy import (
    ACTIONS,
    ATTEMPT_START,
    ALREADY_READY,
    WAIT,
    classify_retry_policy,
)

FLAGS = {"health_ok": True, "audio_ready": True, "sensorhub_ready": False}
SOC_MC = 30000


def snapshot(**overrides):
    base = {
        "gauge_device_type": 42495,
        "capacity_error": 0,
        "temperature_error": 0,
        "current_error": 0,
        "voltage_error": 0,
        "capacity_percent": 60,
        "temperature_millidegrees_celsius": 30000,
        "gauge_current_ma_signed": 0,
        "pack_voltage_mv": 7700,
    }
    base.update(overrides)
    return base


def classify(snapshot_value, soc_mc=SOC_MC, **flags):
    return classify_retry_policy(snapshot_value, soc_mc,
                                 health_ok=flags.get("health_ok", True),
                                 audio_ready=flags.get("audio_ready", True),
                                 sensorhub_ready=flags.get("sensorhub_ready", False))


class DecisionShapeTests(unittest.TestCase):
    def test_decision_has_valid_action_and_reason(self):
        for snap in (snapshot(), snapshot(capacity_percent=22)):
            decision = classify(snap)
            self.assertIn(decision.action, ACTIONS)
            self.assertIsInstance(decision.reason, str)
            self.assertTrue(decision.reason)
            self.assertEqual(decision.as_dict(),
                             {"action": decision.action, "reason": decision.reason})


class AssignedScenarioTests(unittest.TestCase):
    def test_charge_22_percent_charging_waits(self):
        decision = classify(snapshot(capacity_percent=22,
                                     gauge_current_ma_signed=800))
        self.assertEqual(decision.action, WAIT)
        self.assertIn("25", decision.reason)

    def test_charge_25_percent_charging_attempts_start(self):
        decision = classify(snapshot(capacity_percent=25,
                                     gauge_current_ma_signed=300))
        self.assertEqual(decision.action, ATTEMPT_START)

    def test_charge_50_percent_discharging_attempts_start(self):
        # Exactly 50 percent: the charging check only applies below 50.
        decision = classify(snapshot(capacity_percent=50,
                                     gauge_current_ma_signed=-400))
        self.assertEqual(decision.action, ATTEMPT_START)

    def test_hot_battery_waits(self):
        at_limit = classify(snapshot(temperature_millidegrees_celsius=35000))
        above_limit = classify(snapshot(temperature_millidegrees_celsius=36000))
        self.assertEqual(at_limit.action, WAIT)
        self.assertEqual(above_limit.action, WAIT)
        self.assertIn("battery temperature", at_limit.reason)

    def test_invalid_gauge_type_waits(self):
        decision = classify(snapshot(gauge_device_type=42496))
        self.assertEqual(decision.action, WAIT)
        self.assertIn("42495", decision.reason)

    def test_invalid_gauge_error_flag_waits(self):
        decision = classify(snapshot(capacity_error=1))
        self.assertEqual(decision.action, WAIT)
        self.assertIn("capacity_error", decision.reason)

    def test_already_ready_when_audio_and_sensorhub_up(self):
        decision = classify(snapshot(capacity_percent=10),
                            sensorhub_ready=True)
        self.assertEqual(decision.action, ALREADY_READY)


class GateBoundaryTests(unittest.TestCase):
    def test_charge_24_percent_waits_even_while_charging(self):
        decision = classify(snapshot(capacity_percent=24,
                                     gauge_current_ma_signed=900))
        self.assertEqual(decision.action, WAIT)

    def test_below_50_not_charging_waits(self):
        for current in (0, -120):
            decision = classify(snapshot(capacity_percent=45,
                                         gauge_current_ma_signed=current))
            self.assertEqual(decision.action, WAIT, current)
            self.assertIn("charging", decision.reason)

    def test_below_50_charging_attempts_start(self):
        decision = classify(snapshot(capacity_percent=45,
                                     gauge_current_ma_signed=15))
        self.assertEqual(decision.action, ATTEMPT_START)

    def test_soc_at_or_above_45000_waits(self):
        at_limit = classify(snapshot(), soc_mc=45000)
        above_limit = classify(snapshot(), soc_mc=48000)
        self.assertEqual(at_limit.action, WAIT)
        self.assertEqual(above_limit.action, WAIT)
        self.assertIn("SoC", at_limit.reason)

    def test_health_not_ok_waits(self):
        decision = classify(snapshot(), health_ok=False)
        self.assertEqual(decision.action, WAIT)
        self.assertIn("health", decision.reason)

    def test_audio_not_ready_attempts_start(self):
        decision = classify(snapshot(), audio_ready=False)
        self.assertEqual(decision.action, ATTEMPT_START)

    def test_both_services_missing_after_charge_attempts_start(self):
        decision = classify(snapshot(capacity_percent=25,
                                     gauge_current_ma_signed=120),
                            audio_ready=False, sensorhub_ready=False)
        self.assertEqual(decision.action, ATTEMPT_START)

    def test_missing_current_error_waits(self):
        bad = snapshot()
        del bad["current_error"]
        self.assertEqual(classify(bad).action, WAIT)

    def test_sensorhub_up_without_audio_is_not_ready(self):
        decision = classify(snapshot(capacity_percent=10),
                            audio_ready=False, sensorhub_ready=True)
        self.assertEqual(decision.action, WAIT)


class InvalidInputTests(unittest.TestCase):
    def test_none_snapshot_waits(self):
        self.assertEqual(classify(None).action, WAIT)

    def test_non_mapping_snapshot_waits(self):
        self.assertEqual(classify("capacity_percent=60").action, WAIT)

    def test_missing_field_waits(self):
        bad = snapshot()
        del bad["temperature_millidegrees_celsius"]
        decision = classify(bad)
        self.assertEqual(decision.action, WAIT)
        self.assertIn("temperature_millidegrees_celsius", decision.reason)

    def test_non_integer_field_waits(self):
        decision = classify(snapshot(capacity_percent="60"))
        self.assertEqual(decision.action, WAIT)

    def test_boolean_field_waits(self):
        decision = classify(snapshot(capacity_percent=True))
        self.assertEqual(decision.action, WAIT)

    def test_out_of_range_values_wait(self):
        for overrides in ({"capacity_percent": 101},
                          {"capacity_percent": -1},
                          {"temperature_millidegrees_celsius": 90000},
                          {"gauge_current_ma_signed": 50000}):
            decision = classify(snapshot(**overrides))
            self.assertEqual(decision.action, WAIT, overrides)

    def test_invalid_soc_temperature_waits(self):
        for soc in (None, "hot", 120001, -20001, True):
            decision = classify(snapshot(), soc_mc=soc)
            self.assertEqual(decision.action, WAIT, soc)

    def test_invalid_flags_wait(self):
        decision = classify(snapshot(), health_ok="yes")
        self.assertEqual(decision.action, WAIT)
        self.assertIn("flags", decision.reason)


if __name__ == "__main__":
    unittest.main()
