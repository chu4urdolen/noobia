"""Offline fixture tests for the status-only implementation map."""

import copy
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import lynx_status_only_map as smap  # noqa: E402
import lynx_tool_coverage as cov  # noqa: E402
import lynx_tool_manifest as mm  # noqa: E402
from test_lynx_tool_coverage import live_like_snapshot  # noqa: E402

REPO = HERE.parents[2]


def write_map(temp, entries):
    path = Path(temp) / "map.json"
    path.write_text(json.dumps({"components": entries}))
    return path


class MapTest(unittest.TestCase):
    def setUp(self):
        self.entries = smap.load_map()
        self.manifest = mm.build()

    def test_map_matches_coverage_status_only_set(self):
        report = cov.audit(self.manifest)
        self.assertEqual({e["component"] for e in self.entries},
                         set(report["gaps"]["status_only_components"]))
        self.assertEqual(len(self.entries), 15)

    def test_every_cited_path_exists_in_repo(self):
        for path in smap.cited_paths(self.entries):
            self.assertTrue((REPO / path).is_file(), path)

    def test_cited_nrp_lines_name_the_function(self):
        runtime = (REPO / "lynx/tools/lynx_noob_runtime.py").read_text().splitlines()
        checks = {717: "TOUCH_STATUS", 718: "TOUCH_POLL", 726: "GNSS_STATUS",
                  727: "BT_STATUS", 728: "CAMERA_STATUS", 696: "SOC_TEMP"}
        for line, name in checks.items():
            self.assertIn(f'"{name}"', runtime[line - 1], f"line {line}")
        self.assertIn("events.pop", runtime[999 - 1])  # TOUCH_POLL consumes events

    def test_driver_absence_is_separate_from_missing_tool(self):
        result = smap.build(cov.audit(self.manifest, live_like_snapshot()), self.entries)
        rows = {r["component"]: r for r in result["components"]}
        camera = rows["hardware/camera"]
        self.assertEqual(camera["gap"], "trial_needed")
        self.assertFalse(camera["driver_loaded_this_boot"])
        self.assertEqual(rows["platform/touch"]["gap"], "missing_tool")
        self.assertIsNone(rows["platform/touch"]["driver_loaded_this_boot"])
        self.assertTrue(rows["hardware/bluetooth"]["driver_loaded_this_boot"])
        self.assertEqual(rows["platform/battery"]["gap"], "none")
        self.assertEqual([r["priority"] for r in result["components"]], list(range(1, 16)))

    def test_source_only_has_unknown_phone_state(self):
        result = smap.build(cov.audit(self.manifest), self.entries)
        self.assertIsNone(result["snapshot"])
        self.assertTrue(all(r["phone_state"] == "unknown" for r in result["components"]))
        self.assertTrue(all(r["driver_loaded_this_boot"] is None for r in result["components"]))

    def test_attended_stays_separate(self):
        result = smap.build(cov.audit(self.manifest, live_like_snapshot()), self.entries)
        usb = {r["component"]: r for r in result["components"]}["platform/usb"]
        self.assertEqual(usb["attended"], ["usb-acm-2026-11-21"])
        self.assertEqual(usb["phone_state"], "not_ready")  # fixture tree has no UDC

    def test_stale_map_is_rejected(self):
        report = cov.audit(self.manifest)
        with self.assertRaisesRegex(smap.MapError, "stale"):
            smap.build(report, [e for e in self.entries if e["component"] != "platform/sim"])
        report["gaps"]["status_only_components"].remove("platform/touch")
        with self.assertRaisesRegex(smap.MapError, "no longer status-only"):
            smap.build(report, self.entries)

    def test_bad_map_entries_are_rejected(self):
        good = copy.deepcopy(self.entries)
        cases = {
            "duplicate": good + [good[0]],
            "bad kind": [dict(good[0], kind="maybe")] + good[1:],
            "priority gap": [dict(good[0], priority=99)] + good[1:],
            "uncited wrapper": [dict(good[0], existing_routes=[])] + good[1:],
            "empty proof": [dict(good[0], physical_proof_absent=" ")] + good[1:],
            "extra field": [dict(good[0], validated=True)] + good[1:],
        }
        for label, entries in cases.items():
            with self.subTest(label), TemporaryDirectory() as temp:
                with self.assertRaises(smap.MapError):
                    smap.load_map(write_map(temp, entries))

    def test_command_json_and_text(self):
        with TemporaryDirectory() as temp:
            snap = Path(temp) / "snap.json"
            snap.write_text(json.dumps(live_like_snapshot()))
            outputs = []
            for argv in (["--status", str(snap)], ["--status", str(snap)],
                         ["--status", str(snap), "--text"], ["--no-status", "--text"]):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    self.assertEqual(smap.main(argv), 0)
                outputs.append(buf.getvalue())
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(len(json.loads(outputs[0])["components"]), 15)
        self.assertIn("1. platform/touch [missing_tool]", outputs[2])
        self.assertIn("driver NOT loaded this boot", outputs[2])
        self.assertIn("snapshot none (source-only)", outputs[3])


if __name__ == "__main__":
    unittest.main()
