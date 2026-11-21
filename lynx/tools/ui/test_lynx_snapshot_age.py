"""Offline fixture tests: old or different-boot snapshots never look current."""

from datetime import datetime, timedelta, timezone
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import lynx_snapshot_age as age  # noqa: E402
import lynx_status_snapshot as snap  # noqa: E402
import lynx_tool_board as board  # noqa: E402
import lynx_tool_coverage as cov  # noqa: E402
import lynx_tool_manifest as mm  # noqa: E402
from test_lynx_status_board import BOOT, FakeLynx  # noqa: E402

CAPTURED = datetime(2026, 11, 21, 0, 0, tzinfo=timezone.utc)
OTHER_BOOT = "11111111-2222-3333-4444-555555555555"


def fixture(**changes):
    with TemporaryDirectory() as temp:
        data = snap.capture(FakeLynx(Path(temp)), CAPTURED)
    data.update(changes)
    return data


def page(snapshot, now):
    manifest = mm.apply_snapshot(mm.build(), snapshot)
    return board.render(manifest, now)


class FreshnessTest(unittest.TestCase):
    def test_fresh(self):
        f = age.freshness(fixture(), CAPTURED + timedelta(minutes=5))
        self.assertEqual((f["state"], f["current"], f["age_s"]), ("fresh", True, 300))
        self.assertEqual(f["boot_id"], BOOT)
        self.assertEqual(f["boot_state"], "no_previous")

    def test_stale_after_max_age(self):
        f = age.freshness(fixture(), CAPTURED + timedelta(minutes=16))
        self.assertEqual((f["state"], f["current"]), ("stale", False))
        self.assertIn("STALE", f["summary"])

    def test_small_skew_is_tolerated_large_skew_is_flagged(self):
        small = age.freshness(fixture(), CAPTURED - timedelta(seconds=30))
        self.assertEqual((small["state"], small["age_s"]), ("fresh", 0))
        big = age.freshness(fixture(), CAPTURED - timedelta(minutes=10))
        self.assertEqual((big["state"], big["current"]), ("future", False))
        self.assertIn("CLOCK SKEW", big["summary"])

    def test_missing_and_malformed_time(self):
        data = fixture()
        del data["captured_at"]
        self.assertEqual(age.freshness(data, CAPTURED)["state"], "unknown_time")
        for bad in ("yesterday", "2026-11-21 00:00:00", 12345, "2026-13-40T99:00:00Z"):
            with self.subTest(bad=bad):
                f = age.freshness(fixture(captured_at=bad), CAPTURED)
                self.assertEqual(f["state"], "unknown_time" if bad is None else "malformed_time")
                self.assertFalse(f["current"])
                self.assertIsNone(f["age_s"])

    def test_boot_change_and_unknown_boot(self):
        same = fixture(previous={"boot_id": BOOT, "captured_at": "2026-11-20T23:50:00Z"})
        self.assertEqual(age.freshness(same, CAPTURED)["boot_state"], "same_as_previous")
        changed = fixture(previous={"boot_id": OTHER_BOOT, "captured_at": "2026-11-20T23:50:00Z"})
        f = age.freshness(changed, CAPTURED)
        self.assertEqual(f["boot_state"], "changed_since_previous")
        self.assertIn("REBOOTED", f["summary"])
        for bad_boot in (None, {}, {"boot_id": "x; rm -rf /"}, "not a dict"):
            with self.subTest(boot=bad_boot):
                self.assertEqual(age.freshness(fixture(boot=bad_boot), CAPTURED)["boot_state"],
                                 "unknown")

    def test_bad_input_never_raises(self):
        for value in (None, [], "text", {"captured_at": None, "boot": 5, "previous": "x"}):
            self.assertFalse(age.freshness(value, CAPTURED)["current"])

    def test_previous_is_recorded_on_save(self):
        with TemporaryDirectory() as temp:
            out = Path(temp) / "latest.json"
            out.write_text(json.dumps(fixture(boot={"boot_id": OTHER_BOOT},
                                              captured_at="2026-11-20T22:00:00Z")))
            fake = FakeLynx(Path(temp))
            with redirect_stdout(io.StringIO()) as buf:
                self.assertEqual(snap.main(["--out", str(out)], runner=fake), 0)
            report = json.loads(buf.getvalue())
            saved = json.loads(out.read_text())
        self.assertTrue(report["rebooted_since_previous"])
        self.assertEqual(saved["previous"], {"boot_id": OTHER_BOOT,
                                             "captured_at": "2026-11-20T22:00:00Z"})


class BoardAndReportTest(unittest.TestCase):
    def test_fresh_board_has_no_stale_warning(self):
        html = page(fixture(), CAPTURED + timedelta(minutes=2))
        self.assertIn('data-freshness="fresh"', html)
        self.assertNotIn("stale-box", html)
        self.assertIn(f"boot {BOOT}", html)

    def test_stale_board_warns_and_relabels_states(self):
        html = page(fixture(), CAPTURED + timedelta(hours=3))
        self.assertIn('data-freshness="stale"', html)
        self.assertIn("stale-box", html)
        self.assertIn("as captured, not current", html)
        self.assertIn("battery: proven", html)  # still shown, but labelled as history

    def test_board_flags_skew_missing_malformed_and_reboot(self):
        cases = {
            "future": fixture(),
            "unknown_time": fixture(captured_at=None),
            "malformed_time": fixture(captured_at="soon"),
        }
        now = {"future": CAPTURED - timedelta(hours=1)}
        for state, data in cases.items():
            with self.subTest(state=state):
                html = page(data, now.get(state, CAPTURED))
                self.assertIn(f'data-freshness="{state}"', html)
                self.assertIn("stale-box", html)
        rebooted = fixture(previous={"boot_id": OTHER_BOOT, "captured_at": None})
        html = page(rebooted, CAPTURED)
        self.assertIn('data-boot="changed_since_previous"', html)
        self.assertIn("REBOOTED", html)

    def test_attended_evidence_stays_historical(self):
        html = page(fixture(), CAPTURED)  # snapshot boot equals the beep/haptic boot
        self.assertEqual(html.count('data-boot-relation="same_boot"'), 2)
        self.assertIn("still history, not a live check", html)
        self.assertIn("haptic: present, unproven", html)
        other = page(fixture(boot={"boot_id": OTHER_BOOT}), CAPTURED)
        self.assertEqual(other.count('data-boot-relation="earlier_boot"'), 2)
        self.assertEqual(other.count('data-boot-relation="boot_not_recorded"'), 3)

    def test_board_stays_script_free(self):
        html = page(fixture(captured_at="<script>alert(1)</script>"), CAPTURED)
        for tag in ("<script", "<form", "<button", "<input"):
            self.assertNotIn(tag, html.lower())

    def test_coverage_text_reports_freshness(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "snap.json"
            path.write_text(json.dumps(fixture()))
            outs = []
            for now in ("2026-11-21T00:05:00Z", "2026-11-21T03:00:00Z"):
                with redirect_stdout(io.StringIO()) as buf:
                    self.assertEqual(cov.main(["--status", str(path), "--text", "--now", now]), 0)
                outs.append(buf.getvalue())
            with redirect_stdout(io.StringIO()) as buf:
                self.assertEqual(cov.main(["--status", str(path), "--now", "noon"]), 1)
        self.assertIn("snapshot freshness: fresh", outs[0])
        self.assertNotIn("WARNING", outs[0])
        self.assertIn("snapshot freshness: stale", outs[1])
        self.assertIn("WARNING: states below are as captured, not current", outs[1])


if __name__ == "__main__":
    unittest.main()
