#!/usr/bin/env python3
"""Camera sense v2 and the shared camera look (lock, capture, Nexus detection)."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock
import urllib.error

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "common"))
os.environ.setdefault("NOOBIA_AUTONOMY_DIR", str(HERE.parents[2] / "common" / "autonomy"))

import lynx_camera_frame as frame  # noqa: E402
import lynx_sense_camera as cam  # noqa: E402

RAW = b"\x10" * (1600 * 1200)


class Proc:
    def __init__(self, rc=0, report=None, stderr=""):
        self.returncode, self.stderr = rc, stderr
        self.stdout = json.dumps(report or {"state": "frame_captured"}) + "\n"


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener_for(body):
    def opener(req, timeout):
        opener.seen = req
        return Resp(json.dumps(body).encode())
    return opener


class FrameTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.dev, self.helper = d / "video145", d / "capture.py"
        self.dev.write_text("")
        self.helper.write_text("")
        import hashlib
        fw = d / "fw"
        fw.mkdir()
        fw_files = {}
        for name in ("lib3a.ccu_dummy", "remoteproc_scp"):
            (fw / name).write_bytes(name.encode())
            fw_files[name] = hashlib.sha256(name.encode()).hexdigest()
        self.fwpath = d / "fwpath"
        self.fwpath.write_text("/vendor/firmware")
        frame._FW_OK = None
        self.patches = [mock.patch.object(frame, "MEDIA_CTL", "/usr/bin/media-ctl"),
                        mock.patch.object(frame, "DEVICE", self.dev),
                        mock.patch.object(frame, "FW_DIR", fw),
                        mock.patch.object(frame, "FW_FILES", fw_files),
                        mock.patch.object(frame, "FW_PATH", self.fwpath),
                        mock.patch.object(frame, "CAPTURE", str(self.helper)),
                        mock.patch.object(frame, "FRAME", d / "look.bayer"),
                        mock.patch.object(frame, "LOCK", d / "camera.lock"),
                        mock.patch.object(frame, "DISABLE", (d / "off1", d / "off2"))]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def writing_run(self, data=RAW, rc=0, report=None):
        def run(argv, **kw):
            if "--output" not in argv:          # the v4l2-ctl format step
                run.fmt = argv
                return Proc(0)
            run.fw_during = self.fwpath.read_text()
            run.argv = argv
            Path(argv[argv.index("--output") + 1]).write_bytes(data)
            return Proc(rc, report)
        return run

    def test_good_look_sends_raw_frame_and_deletes_it(self):
        op = opener_for({"objects": [{"label": "cell phone", "confidence": 0.61},
                                     {"label": "cat", "confidence": 0.9}], "model_loaded": True})
        r = frame.look(run=self.writing_run(), opener=op)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["items"], "cat(0.90)/cell_phone(0.61)")
        self.assertEqual(r["labels"], ["cat", "cell_phone"])
        self.assertEqual(len(op.seen.data), 1600 * 1200)
        self.assertIn("w=1600&h=1200", op.seen.full_url)
        self.assertFalse(frame.FRAME.exists(), "raw frame must not outlive the look")

    def test_firmware_path_set_only_during_capture_and_restored(self):
        run = self.writing_run()
        frame.look(run=run, opener=opener_for({"objects": []}))
        self.assertEqual(run.fw_during, str(frame.FW_DIR))
        self.assertEqual(self.fwpath.read_text(), "/vendor/firmware")
        self.assertIn("--set-fmt-video=width=1600,height=1200,pixelformat=BA81", run.fmt)
        self.assertIn("--settle-ms", run.argv)
        # Restored even when the capture fails.
        frame.look(run=self.writing_run(rc=1, report={"state": "failed", "error": "x"}),
                   opener=opener_for({}))
        self.assertEqual(self.fwpath.read_text(), "/vendor/firmware")

    def test_refuses_with_unexpected_firmware_path_or_bad_firmware(self):
        self.fwpath.write_text("/somewhere/else")
        r = frame.look(run=self.writing_run(), opener=opener_for({}))
        self.assertIn("unexpected firmware path", r["error"])
        self.fwpath.write_text("/vendor/firmware")
        (frame.FW_DIR / "remoteproc_scp").write_bytes(b"tampered")
        frame._FW_OK = None
        r = frame.look(run=self.writing_run(), opener=opener_for({}))
        self.assertIn("wrong checksum", r["error"])

    def test_no_camera_control_ioctls_requested(self):
        run = self.writing_run()
        frame.look(run=run, opener=opener_for({"objects": []}))
        self.assertNotIn("--request-exposure-lines", run.argv)

    def test_missing_stack_is_honest(self):
        self.dev.unlink()
        r = frame.look(run=self.writing_run(), opener=opener_for({}))
        self.assertFalse(r["ok"])
        self.assertIn("not prepared", r["error"])

    def test_capture_failure_and_wrong_size_and_timeout(self):
        r = frame.look(run=self.writing_run(rc=1, report={"state": "failed", "error": "no frame"}),
                       opener=opener_for({}))
        self.assertFalse(r["ok"])
        self.assertIn("no frame", r["error"])
        r = frame.look(run=self.writing_run(data=b"\x00" * 10), opener=opener_for({}))
        self.assertIn("expected 1920000", r["error"])

        def slow(argv, **kw):
            if "--output" not in argv:
                return Proc(0)
            raise subprocess.TimeoutExpired(argv, 20)
        r = frame.look(run=slow, opener=opener_for({}))
        self.assertIn("timed out", r["error"])
        self.assertEqual(self.fwpath.read_text(), "/vendor/firmware")

        def hung_fmt(argv, **kw):
            raise subprocess.TimeoutExpired(argv, 10)
        r = frame.look(run=hung_fmt, opener=opener_for({}))
        self.assertIn("format step failed", r["error"])

    def test_detector_problems_are_never_an_empty_success(self):
        r = frame.look(run=self.writing_run(), opener=opener_for({"objects": [], "model_loaded": False}))
        self.assertFalse(r["ok"])
        self.assertIn("no model", r["error"])

        def down(req, timeout):
            raise urllib.error.URLError("refused")
        r = frame.look(run=self.writing_run(), opener=down)
        self.assertFalse(r["ok"])
        self.assertIn("unreachable", r["error"])

    def test_lock_makes_a_second_look_busy(self):
        held = threading.Event()
        release = threading.Event()

        def slow_run(argv, **kw):
            if "--output" not in argv:
                return Proc(0)
            held.set()
            release.wait(5)
            Path(argv[argv.index("--output") + 1]).write_bytes(RAW)
            return Proc()
        t = threading.Thread(target=frame.look, kwargs={"run": slow_run, "opener": opener_for({"objects": []})})
        t.start()
        held.wait(5)
        r = frame.look(wait_s=0.0, run=self.writing_run(), opener=opener_for({"objects": []}))
        release.set()
        t.join(5)
        self.assertFalse(r["ok"])
        self.assertTrue(r["busy"])

    def graph_run(self, start="back", fail_link=False):
        """Fake media-ctl that tracks the route, plus capture and format."""
        route = {"now": start}
        calls = []
        def graph():
            def blk(n, sensor, on):
                st = "ENABLED,DYNAMIC" if on else "DYNAMIC"
                return (f'- entity {n}: seninf-x\n  <- "sensor{sensor}":0 [{st}]\n'
                        f'  -> "mtk-cam camsv-0":0 [{st}]\n')
            return blk(27, 4, route["now"] == "back") + blk(53, 2, route["now"] == "wide")
        def run(argv, **kw):
            calls.append(argv)
            if argv[0].endswith("media-ctl"):
                if "-p" in argv:
                    return Proc(0, None) if False else type("P", (), {"returncode": 0, "stdout": graph(), "stderr": ""})()
                spec = argv[-1]
                if fail_link:
                    return type("P", (), {"returncode": 1, "stdout": "", "stderr": "EINVAL"})()
                if spec.startswith("71:0->53:0[5]"):
                    route["now"] = "wide"
                if spec.startswith("45:0->27:0[5]"):
                    route["now"] = "back"
                return type("P", (), {"returncode": 0, "stdout": "", "stderr": ""})()
            if "--output" not in argv:
                return Proc(0)
            sensor = argv[argv.index("--sensor") + 1]
            size = 3264 * 2448 if sensor == "2" else 1600 * 1200
            run.route_during = route["now"]
            Path(argv[argv.index("--output") + 1]).write_bytes(b"\x10" * size)
            return Proc()
        return run, route, calls

    def test_wide_look_switches_route_and_always_back(self):
        run, route, calls = self.graph_run()
        op = opener_for({"objects": [{"label": "tv", "confidence": 0.7}]})
        r = frame.look(run=run, opener=op, camera="wide")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["camera"], "wide")
        self.assertEqual(run.route_during, "wide")
        self.assertEqual(route["now"], "back", "resting route restored")
        self.assertIn("w=3264&h=2448", op.seen.full_url)
        self.assertEqual(len(op.seen.data), 3264 * 2448)
        fmts = [c for c in calls if c[0].endswith("v4l2-ctl")]
        self.assertIn("width=1600,height=1200", fmts[-1][-1], "macro format restored last")

    def test_wide_route_failure_is_honest_and_back_stays(self):
        run, route, calls = self.graph_run(fail_link=True)
        r = frame.look(run=run, opener=opener_for({}), camera="wide")
        self.assertFalse(r["ok"])
        self.assertIn("route link", r["error"])
        self.assertEqual(route["now"], "back")

    def test_disable_switch(self):
        frame.DISABLE[0].write_text("")
        r = frame.look(run=self.writing_run(), opener=opener_for({}))
        self.assertFalse(r["ok"])
        self.assertIn("disabled", r["error"])


class SenseTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = str(Path(self.tmp.name) / "state.json")
        import lynx_senses_lib as lib
        lib._STATE_CACHE.clear()
        self.emit = mock.patch.object(cam, "emit_line", lambda s, p, sn, ev, fields=None, text="", dry_run=False:
                                      f"NOOBIA P{p} {sn} {ev} " + " ".join(f"{k}={v}" for k, v in (fields or {}).items())
                                      + (f" | {text}" if text else ""))
        self.emit.start()
        self.nodis = mock.patch.object(cam.frame, "disabled", lambda: None)
        self.nodis.start()

    def tearDown(self):
        self.emit.stop()
        self.nodis.stop()
        self.tmp.cleanup()

    def step(self, result, t, boot="b1"):
        res, code = cam.run(state_file=self.state, look=lambda wait_s, camera="back": result, now=t, boot=boot)
        self.assertEqual(code, 0)
        return res["emitted"]

    def seen(self, *pairs):
        objs = [{"label": l, "confidence": c} for l, c in pairs]
        return {"ok": True, "camera": "back", "objects": objs,
                "items": frame.items_text(objs), "labels": [frame.clean_label(l) for l, _ in pairs]}

    def test_one_line_per_frame_p1_when_new(self):
        lines = self.step(self.seen(("laptop", 0.75), ("person", 0.87), ("cat", 0.45)), 1000)
        self.assertEqual(lines, ["NOOBIA P1 camera objects.seen cam=back n=3 | laptop(0.75)/person(0.87)/cat(0.45)"])

    def test_repeat_is_p0_and_a_new_label_is_p1_again(self):
        self.step(self.seen(("laptop", 0.75)), 1000)
        self.assertTrue(self.step(self.seen(("laptop", 0.74)), 1060)[0].startswith("NOOBIA P0 camera objects.seen"))
        self.assertTrue(self.step(self.seen(("laptop", 0.74), ("cat", 0.6)), 1120)[0].startswith("NOOBIA P1"))
        self.assertTrue(self.step(self.seen(("laptop", 0.74)), 1120 + 301)[0].startswith("NOOBIA P1"))

    def test_empty_frame(self):
        lines = self.step(self.seen(), 1000)
        self.assertEqual(lines, ["NOOBIA P0 camera frame.analyzed objects=0 cam=back | frame analyzed, no objects recognized"])

    def test_busy_skips_quietly(self):
        self.assertEqual(self.step({"ok": False, "busy": True, "error": "camera is in use"}, 1000), [])

    def test_alternates_back_and_wide(self):
        used = []
        for t in range(4):
            cam.run(state_file=self.state, now=1000 + 60 * t, boot="b1",
                    look=lambda wait_s, camera="back": used.append(camera) or self.seen(("cat", 0.9)))
        self.assertEqual(used, ["back", "wide", "back", "wide"])

    def test_a_failing_camera_is_dropped_the_other_goes_on_then_pause(self):
        bad = {"ok": False, "busy": False, "error": "capture failed: no frame within 9 seconds"}
        used, lines = [], []
        def look(wait_s, camera="back"):
            used.append(camera)
            return bad if camera == "wide" else self.seen(("cat", 0.9))
        for t in range(8):
            r, _ = cam.run(state_file=self.state, look=look, now=1000 + 60 * t, boot="b1")
            lines += r["emitted"]
        self.assertEqual(used[:6], ["back", "wide", "back", "wide", "back", "wide"])
        self.assertEqual(used[6:], ["back", "back"], "wide dropped after 3 failures, back goes on")
        self.assertEqual(len([l for l in lines if "unavailable cam=wide" in l]), 1)
        # Both failing: back too is paused after 3, then nothing is touched this boot.
        def all_bad(wait_s, camera="back"):
            used.append(camera)
            return bad
        for t in range(8, 12):
            r, _ = cam.run(state_file=self.state, look=all_bad, now=1000 + 60 * t, boot="b1")
            lines += r["emitted"]
        self.assertTrue(any(l.startswith("NOOBIA P3 camera unavailable") for l in lines))
        n = len(used)
        cam.run(state_file=self.state, look=all_bad, now=2000, boot="b1")
        self.assertEqual(len(used), n, "a fully paused camera is not touched again this boot")
        self.assertTrue(self.step(self.seen(("cat", 0.9)), 3000, boot="b2")[0].startswith("NOOBIA P1"))

    def test_not_prepared_is_not_a_failure(self):
        absent = {"ok": False, "busy": False, "error": "/dev/video145 absent: camera stack not prepared for this boot"}
        for t in range(1000, 1600, 60):
            self.assertEqual(self.step(absent, t), [])
        # Once prepared, the very next look works: no pause was ever taken.
        self.assertTrue(self.step(self.seen(("cat", 0.9)), 1700)[0].startswith("NOOBIA P1"))

    def test_success_resets_the_failure_count(self):
        bad = {"ok": False, "busy": False, "error": "x"}
        self.step(bad, 1000)
        self.step(bad, 1060)
        self.step(self.seen(("cat", 0.9)), 1120)
        self.assertEqual(self.step(bad, 1180), [])
        self.assertEqual(self.step(bad, 1240), [])

    def test_line_feeds_the_templated_pattern(self):
        sys.path.insert(0, os.environ["NOOBIA_AUTONOMY_DIR"])
        import ranker
        import sense
        line = self.step(self.seen(("laptop", 0.7534), ("person", 0.87), ("cat", 0.45)), 1000)[0]
        pats = json.loads((HERE.parents[1] / "autonomy" / "patterns-lynx.json").read_text())["store"]
        pat = next(p for p in pats if p["id"] == "camera-objects")
        self.assertEqual(ranker.render_message(pat, sense.parse_line(line)),
                         "With your back camera you see laptop, person, cat.")


if __name__ == "__main__":
    unittest.main()
