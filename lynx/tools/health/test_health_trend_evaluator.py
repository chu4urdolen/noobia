"""Hermetic tests for health_trend_evaluator (D16, round 6).

Pure offline: no network, no subprocesses, no clock reads — the evaluator
works only from the documents' own captured_at timestamps.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import health_trend_evaluator as hte  # noqa: E402

EXAMPLES = os.path.join(os.path.dirname(__file__), "examples")


def ex(name):
    return os.path.join(EXAMPLES, name)


def doc(cap=None, free=None, maxc=None, xid=None, gput=None, t="2026-11-21T10:00:00Z",
        gauge=None, volt=None, schema="portable-health/1"):
    d = {"schema": schema, "host": "lynx", "profile": "lynx"}
    if t is not None:
        d["captured_at"] = t
    battery = {}
    if cap is not None:
        battery["capacity_percent"] = cap
    if volt is not None:
        battery["voltage_mv"] = volt
    if gauge is not None:
        battery["gauge_read_errors"] = gauge
    facts = {}
    if battery:
        facts["battery"] = battery
    if free is not None:
        facts["storage"] = {"free_mib": free}
    if maxc is not None:
        facts["thermal"] = {"max_c": maxc}
    if facts:
        d["facts"] = facts
    machine = {}
    if xid is not None:
        machine["xid_count"] = xid
    if gput is not None:
        machine["temp_c"] = gput
    if machine:
        d["machine"] = {"nexus": machine}
    return d


class FixtureSuiteTests(unittest.TestCase):
    def test_stable_is_ok_exit0(self):
        rc = hte.main([ex("trend-stable.json")])
        self.assertEqual(rc, 0)
        rep = hte.evaluate_series(hte.load_series([ex("trend-stable.json")]))
        self.assertEqual(rep["verdict"], "ok")
        self.assertEqual(rep["metrics"]["battery_drain"]["status"], "ok")
        self.assertAlmostEqual(rep["metrics"]["battery_drain"]["capacity_pct_per_hr"], -0.5)
        self.assertEqual(rep["metrics"]["storage"]["status"], "ok")
        self.assertIn("no monotonic accumulation", rep["metrics"]["storage"]["note"])

    def test_draining_is_warn_exit1(self):
        rc = hte.main([ex("trend-draining.json")])
        self.assertEqual(rc, 1)
        rep = hte.evaluate_series(hte.load_series([ex("trend-draining.json")]))
        m = rep["metrics"]["battery_drain"]
        self.assertEqual(m["capacity_pct_per_hr_status"], "warn")
        self.assertEqual(m["voltage_mv_per_hr_status"], "warn")
        self.assertEqual(rep["verdict"], "warn")

    def test_storage_leak_is_warn_exit1(self):
        rc = hte.main([ex("trend-storage-leak.json")])
        self.assertEqual(rc, 1)
        rep = hte.evaluate_series(hte.load_series([ex("trend-storage-leak.json")]))
        m = rep["metrics"]["storage"]
        self.assertEqual(m["total_drop_status"], "warn")
        self.assertEqual(m["rate_status"], "warn")
        self.assertEqual(m["monotonic_fall_mib"], 863.0)

    def test_xid_cascade_is_fail_exit2(self):
        rc = hte.main([ex("trend-xid-cascade.json")])
        self.assertEqual(rc, 2)
        rep = hte.evaluate_series(hte.load_series([ex("trend-xid-cascade.json")]))
        m = rep["metrics"]["fault_counters"]
        self.assertEqual(m["xid_status"], "fail")
        self.assertEqual(m["xid_max_step"], 5.0)  # steps: 1->4 (3), 4->9 (5)
        self.assertEqual(m["xid_total_delta"], 8.0)
        self.assertEqual(rep["verdict"], "fail")

    def test_insufficient_is_exit3(self):
        rc = hte.main([ex("trend-insufficient.json")])
        self.assertEqual(rc, 3)
        rep = hte.evaluate_series(hte.load_series([ex("trend-insufficient.json")]))
        self.assertEqual(rep["verdict"], "insufficient")
        for name in ("battery_drain", "storage", "fault_counters", "thermal"):
            self.assertEqual(rep["metrics"][name]["status"], "absent")


class ValidationTests(unittest.TestCase):
    def test_single_document_rejected(self):
        with self.assertRaises(hte.TrendError):
            hte.evaluate_series([doc(cap=90)])

    def test_bad_schema_rejected(self):
        with self.assertRaises(hte.TrendError):
            hte.evaluate_series([doc(schema="other/9"), doc(cap=90, t="2026-11-21T11:00:00Z")])

    def test_no_shape_rejected(self):
        docs = [{"schema": "portable-health/1", "host": "lynx"}] * 2
        with self.assertRaises(hte.TrendError):
            hte.evaluate_series(docs)

    def test_missing_file_rejected(self):
        with self.assertRaises(hte.TrendError):
            hte.load_series([ex("does-not-exist.json")])

    def test_too_many_docs_rejected(self):
        docs = [doc(cap=90 - i * 0.01, t=f"2026-11-21T{10 + i:02d}:00:00Z")
                for i in range(hte.MAX_DOCS + 1)]
        with self.assertRaises(hte.TrendError):
            hte.evaluate_series(docs)

    def test_usage_no_paths_is_exit4(self):
        self.assertEqual(hte.main([]), 4)


class BatteryTrendTests(unittest.TestCase):
    def test_no_timestamps_is_insufficient(self):
        docs = [
            {"schema": "portable-health/1", "host": "lynx",
             "facts": {"battery": {"capacity_percent": 90.0}}},
            {"schema": "portable-health/1", "host": "lynx",
             "facts": {"battery": {"capacity_percent": 80.0}}},
        ]
        rep = hte.evaluate_series(docs)
        self.assertEqual(rep["metrics"]["battery_drain"]["status"], "insufficient")
        self.assertEqual(rep["verdict"], "insufficient")

    def test_voltage_optional_absent_never_ok_invented(self):
        docs = [doc(cap=90, volt=None, t="2026-11-21T10:00:00Z"),
                doc(cap=80, volt=None, t="2026-11-21T11:00:00Z")]
        rep = hte.evaluate_series(docs)
        m = rep["metrics"]["battery_drain"]
        self.assertEqual(m["voltage_points"], 0)
        self.assertIsNone(m["voltage_mv_per_hr"])
        self.assertNotIn("voltage_mv_per_hr_status", m)

    def test_battery_fail_band(self):
        docs = [doc(cap=90, t="2026-11-21T10:00:00Z"),
                doc(cap=60, t="2026-11-21T11:00:00Z")]  # 30%/hr >= 25 -> fail
        rep = hte.evaluate_series(docs)
        self.assertEqual(rep["metrics"]["battery_drain"]["capacity_pct_per_hr_status"], "fail")
        self.assertEqual(rep["verdict"], "fail")


class StorageTrendTests(unittest.TestCase):
    def test_single_dip_not_monotonic_is_ok(self):
        docs = [doc(free=214000, t="2026-11-21T10:00:00Z"),
                doc(free=213000, t="2026-11-21T11:00:00Z"),
                doc(free=214200, t="2026-11-21T12:00:00Z")]
        rep = hte.evaluate_series(docs)
        self.assertEqual(rep["metrics"]["storage"]["status"], "ok")
        self.assertIn("no monotonic accumulation", rep["metrics"]["storage"]["note"])

    def test_storage_fail_band(self):
        docs = [doc(free=220000, t="2026-11-21T10:00:00Z"),
                doc(free=210000, t="2026-11-21T11:00:00Z")]  # 10000 MiB >= 2048 -> fail
        rep = hte.evaluate_series(docs)
        self.assertEqual(rep["metrics"]["storage"]["total_drop_status"], "fail")
        self.assertEqual(rep["verdict"], "fail")

    def test_used_pct_rise_warn(self):
        d1 = {"schema": "portable-health/1", "host": "lynx",
              "captured_at": "2026-11-21T10:00:00Z",
              "facts": {"storage": {"used_percent": 40.0}}}
        d2 = {"schema": "portable-health/1", "host": "lynx",
              "captured_at": "2026-11-21T12:00:00Z",
              "facts": {"storage": {"used_percent": 46.0}}}
        rep = hte.evaluate_series([d1, d2])
        self.assertEqual(rep["metrics"]["storage"]["rise_status"], "warn")


class FaultCounterTests(unittest.TestCase):
    def test_single_step_is_warn(self):
        docs = [doc(xid=1, t="2026-11-21T10:00:00Z"),
                doc(xid=2, t="2026-11-21T11:00:00Z")]
        rep = hte.evaluate_series(docs)
        self.assertEqual(rep["metrics"]["fault_counters"]["xid_status"], "warn")

    def test_flat_counters_ok(self):
        docs = [doc(xid=3, t="2026-11-21T10:00:00Z"),
                doc(xid=3, t="2026-11-21T11:00:00Z")]
        rep = hte.evaluate_series(docs)
        self.assertEqual(rep["metrics"]["fault_counters"]["xid_status"], "ok")

    def test_gauge_errors_warn_and_fail(self):
        docs = [doc(gauge=0, t="2026-11-21T10:00:00Z"),
                doc(gauge=1, t="2026-11-21T11:00:00Z")]
        rep = hte.evaluate_series(docs)
        self.assertEqual(rep["metrics"]["fault_counters"]["gauge_status"], "warn")
        docs = [doc(gauge=0, t="2026-11-21T10:00:00Z"),
                doc(gauge=3, t="2026-11-21T11:00:00Z")]
        rep = hte.evaluate_series(docs)
        self.assertEqual(rep["metrics"]["fault_counters"]["gauge_status"], "fail")


class ThermalTests(unittest.TestCase):
    def test_drift_warn(self):
        docs = [doc(maxc=30.0, t="2026-11-21T10:00:00Z"),
                doc(maxc=38.0, t="2026-11-21T12:00:00Z")]  # 4 C/hr >= 3 -> warn
        rep = hte.evaluate_series(docs)
        m = rep["metrics"]["thermal"]
        self.assertEqual(m["drift_status"], "warn")
        self.assertEqual(m["level_status"], "ok")

    def test_generic_level_band(self):
        docs = [doc(maxc=44.0, t="2026-11-21T10:00:00Z"),
                doc(maxc=46.0, t="2026-11-21T11:00:00Z")]  # last >= 45 -> warn
        rep = hte.evaluate_series(docs)
        self.assertEqual(rep["metrics"]["thermal"]["level_status"], "warn")
        docs = [doc(maxc=58.0, t="2026-11-21T10:00:00Z"),
                doc(maxc=61.0, t="2026-11-21T11:00:00Z")]  # last >= 60 -> fail
        rep = hte.evaluate_series(docs)
        self.assertEqual(rep["metrics"]["thermal"]["level_status"], "fail")

    def test_gpu_band(self):
        docs = [doc(gput=80.0, t="2026-11-21T10:00:00Z"),
                doc(gput=86.0, t="2026-11-21T11:00:00Z")]
        rep = hte.evaluate_series(docs)
        self.assertEqual(rep["metrics"]["thermal"]["gpu_level_status"], "warn")
        docs = [doc(gput=90.0, t="2026-11-21T10:00:00Z"),
                doc(gput=96.0, t="2026-11-21T11:00:00Z")]
        rep = hte.evaluate_series(docs)
        self.assertEqual(rep["metrics"]["thermal"]["gpu_level_status"], "fail")


class ReportShapeTests(unittest.TestCase):
    """Evaluated-report shape (checks[] evidence) must feed the same series."""

    def _rep(self, cap, xid, t):
        return {
            "schema": "portable-health/1",
            "host": "nexus",
            "profile": "nexus",
            "captured_at": t,
            "verdict": "ok",
            "checks": [
                {"name": "battery", "scope": "common", "status": "ok",
                 "evidence": {"capacity_percent": cap}},
                {"name": "nexus/gpu", "scope": "machine", "status": "ok",
                 "evidence": {"xid_count": xid, "temp_c": 60.0}},
            ],
        }

    def test_extraction(self):
        docs = [self._rep(90, 1, "2026-11-21T10:00:00Z"),
                self._rep(75, 4, "2026-11-21T11:00:00Z")]
        rep = hte.evaluate_series(docs)
        m = rep["metrics"]["battery_drain"]
        self.assertAlmostEqual(m["capacity_pct_per_hr"], -15.0)
        self.assertEqual(m["capacity_pct_per_hr_status"], "warn")
        self.assertEqual(rep["metrics"]["fault_counters"]["xid_status"], "fail")


class OutputTests(unittest.TestCase):
    def test_json_output_is_parseable(self):
        import subprocess
        out = subprocess.run(
            [sys.executable, os.path.join(os.path.dirname(__file__), "health_trend_evaluator.py"),
             ex("trend-stable.json"), "--json"],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(out.returncode, 0)
        payload = json.loads(out.stdout)
        self.assertEqual(payload["schema"], "portable-health-trend/1")
        self.assertEqual(payload["docs"], 3)
        self.assertEqual(payload["verdict"], "ok")

    def test_pure_module_no_network_imports(self):
        banned = {"socket", "subprocess", "urllib", "http", "ssl"}
        import_module_names = set()
        import ast
        tree = ast.parse(open(os.path.join(os.path.dirname(__file__),
                                          "health_trend_evaluator.py")).read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                import_module_names.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                import_module_names.add(node.module.split(".")[0])
        self.assertTrue(import_module_names.isdisjoint(banned),
                        f"unexpected imports: {import_module_names & banned}")


if __name__ == "__main__":
    unittest.main()
