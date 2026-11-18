#!/usr/bin/env python3
"""Unit tests for Aigel's sentinel (threshold alerts over vitals facts)."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from aigel_sentinel import (
    DEFAULT_THRESHOLDS,
    _extract_metric,
    _severity_for,
    apply_cooldown,
    evaluate,
    load_config,
    merge_thresholds,
    record_alerts,
)

FACTS = {
    "cpu": {"ram_free_pct": 7.7, "load1": 12.0, "cores_count": 16, "timestamp": "t"},
    "net": {"wifi_state": "UP", "dns_rtt_ms": 120.0, "timestamp": "t"},
    "disk": {"max_used_pct": 96, "max_used_device": "/dev/nvme0n1p3", "mounts": [], "timestamp": "t"},
    "mem": {"ram_used": "x", "ram_total": "y", "vram_used_mb": 100, "timestamp": "t"},
    "gpu": {"temp_c": 88.0, "power_w": 300.0, "file": "g.csv"},
    "journal_errors": {"minutes": 60, "count": 12, "lines": ["e"]},
    "lighthouse": {"nexus_ready": True, "online": ["gateway", "nexus"], "offline": []},
}


class TestSeverityFor(unittest.TestCase):
    def test_high_direction_crossing(self) -> None:
        rule = {"direction": "high", "warn": 90, "fail": 95}
        self.assertEqual(_severity_for(96, rule), "fail")
        self.assertEqual(_severity_for(91, rule), "warn")
        self.assertIsNone(_severity_for(50, rule))

    def test_low_direction_crossing(self) -> None:
        rule = {"direction": "low", "warn": 10, "fail": 2}
        self.assertEqual(_severity_for(1.5, rule), "fail")
        self.assertEqual(_severity_for(5.0, rule), "warn")
        self.assertIsNone(_severity_for(50.0, rule))

    def test_boolean_expect(self) -> None:
        rule = {"expect": True, "severity": "fail"}
        self.assertEqual(_severity_for(False, rule), "fail")
        self.assertIsNone(_severity_for(True, rule))

    def test_membership(self) -> None:
        rule = {"bad": ["DOWN"], "severity": "fail"}
        self.assertEqual(_severity_for("DOWN", rule), "fail")
        self.assertIsNone(_severity_for("UP", rule))

    def test_non_numeric_value_skipped(self) -> None:
        self.assertIsNone(_severity_for("DOWN", {"direction": "high", "warn": 1, "fail": 2}))

    def test_unknown_rule_shape(self) -> None:
        self.assertIsNone(_severity_for(5, {"whatever": 1}))


class TestMergeThresholds(unittest.TestCase):
    def test_config_overrides_per_metric(self) -> None:
        config = {"thresholds": {"gpu_temp_c": {"warn": 80}}}
        merged = merge_thresholds(config)
        self.assertEqual(merged["gpu_temp_c"]["warn"], 80)
        self.assertEqual(merged["gpu_temp_c"]["fail"], 95)  # inherited from defaults
        self.assertEqual(merged["disk_used_pct"], DEFAULT_THRESHOLDS["disk_used_pct"])

    def test_config_can_add_new_metric(self) -> None:
        config = {"thresholds": {"fan_rpm": {"direction": "low", "warn": 800, "fail": 500}}}
        merged = merge_thresholds(config)
        self.assertIn("fan_rpm", merged)
        self.assertEqual(merged["fan_rpm"]["warn"], 800)

    def test_none_and_garbage_are_safe(self) -> None:
        self.assertEqual(merge_thresholds(None), {k: dict(v) for k, v in DEFAULT_THRESHOLDS.items()})
        merged = merge_thresholds({"thresholds": {"disk_used_pct": "not-a-dict"}})
        self.assertEqual(merged["disk_used_pct"], DEFAULT_THRESHOLDS["disk_used_pct"])


class TestLoadConfig(unittest.TestCase):
    def setUp(self) -> None:
        self._old = os.environ.pop("AIGEL_CONFIG", None)

    def tearDown(self) -> None:
        if self._old is None:
            os.environ.pop("AIGEL_CONFIG", None)
        else:
            os.environ["AIGEL_CONFIG"] = self._old

    def test_missing_file_yields_empty(self) -> None:
        self.assertEqual(load_config("/nonexistent/config.json"), {})

    def test_malformed_file_yields_empty(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            handle.write("{ no json")
            name = handle.name
        try:
            self.assertEqual(load_config(name), {})
        finally:
            Path(name).unlink()

    def test_env_override(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump({"thresholds": {"gpu_temp_c": {"warn": 1}}}, handle)
            name = handle.name
        try:
            os.environ["AIGEL_CONFIG"] = name
            config = load_config()
            self.assertEqual(config["thresholds"]["gpu_temp_c"]["warn"], 1)
        finally:
            os.environ.pop("AIGEL_CONFIG", None)
            Path(name).unlink()

    def test_non_dict_json_yields_empty(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            handle.write("[1, 2, 3]")
            name = handle.name
        try:
            self.assertEqual(load_config(name), {})
        finally:
            Path(name).unlink()


class TestExtractMetric(unittest.TestCase):
    def test_disk(self) -> None:
        value, detail = _extract_metric(FACTS, "disk_used_pct")
        self.assertEqual(value, 96)
        self.assertIn("/dev/nvme0n1p3", detail)

    def test_gpu_prefers_store_then_live(self) -> None:
        value, detail = _extract_metric(FACTS, "gpu_temp_c")
        self.assertEqual(value, 88.0)
        facts = {k: v for k, v in FACTS.items() if k != "gpu"}
        facts["gpu_live"] = {"temp_c": 77.0, "name": "Ada"}
        value, detail = _extract_metric(facts, "gpu_temp_c")
        self.assertEqual(value, 77.0)
        self.assertIn("live", detail)

    def test_load_per_core(self) -> None:
        value, _ = _extract_metric(FACTS, "load1_per_core")
        self.assertAlmostEqual(value, 0.75)

    def test_missing_metric_is_none(self) -> None:
        self.assertIsNone(_extract_metric({}, "wifi_state"))
        self.assertIsNone(_extract_metric(FACTS, "fan_rpm"))
        self.assertIsNone(_extract_metric({"journal_errors": {"count": None}}, "journal_error_count"))


class TestEvaluate(unittest.TestCase):
    def test_fires_expected_alerts(self) -> None:
        alerts = evaluate(FACTS)
        metrics = {a["metric"] for a in alerts}
        self.assertIn("disk_used_pct", metrics)          # 96 >= 95 fail
        self.assertIn("ram_free_pct", metrics)           # 7.7 <= 10 warn
        self.assertIn("gpu_temp_c", metrics)             # 88 >= 85 warn
        self.assertIn("journal_error_count", metrics)    # 12 >= 10 warn
        self.assertNotIn("dns_rtt_ms", metrics)          # 120 < 150
        self.assertNotIn("wifi_state", metrics)          # UP
        self.assertNotIn("nexus_ready", metrics)         # True

    def test_fail_alerts_sort_first(self) -> None:
        alerts = evaluate(FACTS)
        self.assertEqual([a["severity"] for a in alerts], ["fail", "warn", "warn", "warn"])

    def test_message_shape(self) -> None:
        alert = next(a for a in evaluate(FACTS) if a["metric"] == "disk_used_pct")
        self.assertEqual(alert["severity"], "fail")
        self.assertEqual(alert["value"], 96)
        self.assertIn("96", alert["message"])
        self.assertIn("warn 90 / fail 95", alert["message"])

    def test_overridden_thresholds_change_outcome(self) -> None:
        merged = merge_thresholds({"thresholds": {"disk_used_pct": {"warn": 99, "fail": 99}}})
        alerts = evaluate(FACTS, merged)
        self.assertNotIn("disk_used_pct", {a["metric"] for a in alerts})

    def test_quiet_facts_yield_no_alerts(self) -> None:
        facts = {
            "cpu": {"ram_free_pct": 40.0, "load1": 0.5, "cores_count": 16},
            "net": {"wifi_state": "UP", "dns_rtt_ms": 20.0},
            "disk": {"max_used_pct": 40, "max_used_device": "/dev/sda1"},
            "journal_errors": {"count": 0, "minutes": 60},
            "lighthouse": {"nexus_ready": True, "offline": []},
            "gpu": {"temp_c": 50.0},
        }
        self.assertEqual(evaluate(facts), [])


class TestRecordAlerts(unittest.TestCase):
    def test_writes_when_directory_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = os.path.join(tmp, "aigel.log")
            alerts = evaluate(FACTS)
            lines, written = record_alerts(alerts, log, timestamp="2026-11-18T21:00:00Z")
            self.assertTrue(written)
            self.assertEqual(len(lines), len(alerts))
            content = Path(log).read_text()
            self.assertTrue(all(line in content for line in lines))
            first = lines[0]
            self.assertTrue(first.startswith("2026-11-18T21:00:00Z ALERT [fail] disk_used_pct=96"))

    def test_no_write_when_directory_missing(self) -> None:
        alerts = evaluate(FACTS)
        lines, written = record_alerts(alerts, "/nonexistent/dir/aigel.log")
        self.assertFalse(written)
        self.assertEqual(len(lines), len(alerts))

    def test_no_alerts_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = os.path.join(tmp, "aigel.log")
            lines, written = record_alerts([], log)
            self.assertEqual(lines, [])
            self.assertFalse(written)
            self.assertFalse(os.path.exists(log))


class TestApplyCooldown(unittest.TestCase):
    def test_suppresses_within_window(self) -> None:
        alerts = [{"metric": "disk_used_pct", "severity": "fail"},
                  {"metric": "ram_free_pct", "severity": "warn"}]
        state = {"alerts": {"disk_used_pct": 1000.0}}
        kept, new_state = apply_cooldown(alerts, state, now=1100.0, cooldown_s=300.0)
        self.assertEqual([a["metric"] for a in kept], ["ram_free_pct"])
        self.assertIn("disk_used_pct", new_state["alerts"])  # unchanged
        self.assertEqual(new_state["alerts"]["ram_free_pct"], 1100.0)

    def test_reports_again_after_window(self) -> None:
        alerts = [{"metric": "disk_used_pct", "severity": "fail"}]
        state = {"alerts": {"disk_used_pct": 1000.0}}
        kept, _ = apply_cooldown(alerts, state, now=1400.0, cooldown_s=300.0)
        self.assertEqual(len(kept), 1)

    def test_zero_cooldown_disables(self) -> None:
        alerts = [{"metric": "disk_used_pct", "severity": "fail"}]
        state = {"alerts": {"disk_used_pct": 999999.0}}
        kept, _ = apply_cooldown(alerts, state, now=1000.0, cooldown_s=0.0)
        # cooldown 0 means (now - last) < 0 is never true
        self.assertEqual(len(kept), 1)

    def test_garbage_state_is_safe(self) -> None:
        alerts = [{"metric": "gpu_temp_c", "severity": "warn"}]
        kept, state = apply_cooldown(alerts, {"alerts": "garbage"}, now=1.0, cooldown_s=100.0)
        self.assertEqual(len(kept), 1)
        self.assertEqual(state["alerts"]["gpu_temp_c"], 1.0)


if __name__ == "__main__":
    unittest.main()
