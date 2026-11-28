#!/usr/bin/env python3
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
os.environ["LYNX_SENSES_ROOT"] = str(HERE.parents[1] / "senses")
os.environ.setdefault("NOOBIA_AUTONOMY_DIR", str(HERE.parents[2] / "common" / "autonomy"))
sys.path.insert(0, str(HERE))
import lynx_camera_photo as photo  # noqa: E402


class PhotoTest(unittest.TestCase):
    def run_main(self, look_result, stdin="{}"):
        lines = []
        with mock.patch.object(photo.frame, "look", lambda wait_s, camera="back": look_result), \
                mock.patch("lynx_senses_lib.emit_line",
                           lambda s, p, sn, ev, fields=None, text="", dry_run=False:
                           lines.append((p, sn, ev, dict(fields or {}), text)) or "line"), \
                mock.patch("sys.stdin", io.StringIO(stdin)), \
                mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            code = photo.main()
        return code, json.loads(out.getvalue()), lines

    def test_sees_and_logs_as_self_single_camera(self):
        objs = [{"label": "cat", "confidence": 0.91}, {"label": "cell_phone", "confidence": 0.6}]
        code, out, lines = self.run_main({"ok": True, "camera": "back", "objects": objs,
                                          "items": "cat(0.91)/cell_phone(0.60)",
                                          "labels": ["cat", "cell_phone"]},
                                         stdin=json.dumps({"camera": "back"}))
        self.assertEqual(code, 0)
        self.assertEqual(out["you_see"], "cat, cell phone")
        self.assertTrue(out["logged"])
        self.assertEqual(lines[0][0], 0)
        self.assertEqual(lines[0][3]["cause"], "self")     # context only, never a trigger
        self.assertEqual(lines[0][2], "objects.seen")

    def test_sees_dual_camera_by_default(self):
        objs = [{"label": "person", "confidence": 0.95}]
        code, out, lines = self.run_main({"ok": True, "camera": "front", "objects": objs,
                                          "items": "person(0.95)",
                                          "labels": ["person"]})
        self.assertEqual(code, 0)
        self.assertEqual(out["camera"], "both")
        self.assertIn("In front: person", out["you_see"])
        self.assertTrue(out["logged"])

    def test_failure_is_honest(self):
        code, out, lines = self.run_main({"ok": False, "error": "camera stack not prepared"})
        self.assertEqual(code, 1)
        self.assertFalse(out["ok"])
        self.assertIn("not prepared", out["error"])
        self.assertEqual(lines, [])


if __name__ == "__main__":
    unittest.main()
