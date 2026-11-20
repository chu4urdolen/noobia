"""Unit tests for :mod:`aria.inference.analyze_reset_monitor`.

The tests create small JSONL snippets to exercise the behaviour required by
the task description:

* Multiple contiguous boot segments.
* Records missing the ``gpu`` key or containing non‑numeric values.
* Malformed JSON lines.

The expected output is compared against the actual ``analyze_reset_monitor``
function result.  The tests are self‑contained and do not touch the real
``/noobia/aria/logs/nexus-reset-monitor.jsonl`` file.
"""

import json
import tempfile
from pathlib import Path
import unittest

from aria.inference.analyze_reset_monitor import analyze_reset_monitor


def _write_jsonl(lines: list[str]) -> Path:
    tmp = Path(tempfile.mkstemp(prefix="reset_monitor_test_", suffix=".jsonl")[1])
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return tmp


class TestAnalyzeResetMonitor(unittest.TestCase):
    def test_multiple_segments(self):
        lines = [
            json.dumps({"boot_id": "A", "time": 1, "gpu": ["30", "100", "50", "1500"]}),
            json.dumps({"boot_id": "A", "time": 2, "gpu": ["31", "110", "55", "1501"]}),
            json.dumps({"boot_id": "B", "time": 3, "gpu": ["32", "120", "60", "1502"]}),
            json.dumps({"boot_id": "B", "time": 4, "gpu": ["33", "130", "65", "1503"]}),
            json.dumps({"boot_id": "B", "time": 5, "gpu": ["34", "140", "70", "1504"]}),
        ]
        path = _write_jsonl(lines)
        segs = analyze_reset_monitor(path)
        self.assertEqual(len(segs), 2)
        self.assertEqual(segs[0].boot_id, "A")
        self.assertEqual(segs[0].sample_count, 2)
        self.assertEqual(segs[0].max_gpu_watts, 110)
        self.assertEqual(segs[0].max_gpu_util, 55)
        self.assertEqual(segs[0].first_ts, 1)
        self.assertEqual(segs[0].last_ts, 2)
        self.assertEqual(segs[0].segment_index, 0)
        self.assertFalse(segs[0].incomplete)
        self.assertEqual(segs[1].boot_id, "B")
        self.assertEqual(segs[1].sample_count, 3)
        self.assertEqual(segs[1].max_gpu_watts, 140)
        self.assertEqual(segs[1].max_gpu_util, 70)
        self.assertEqual(segs[1].segment_index, 0)
        path.unlink()

    def test_missing_gpu_data(self):
        lines = [
            json.dumps({"boot_id": "C", "time": 10, "gpu": ["35", "150", "75", "1505"]}),
            json.dumps({"boot_id": "C", "time": 11, "gpu": ["36", "nan", "80", "1506"]}),  # malformed
            json.dumps({"boot_id": "C", "time": 12, "gpu": ["37", "160", "85", "1507"]}),
        ]
        path = _write_jsonl(lines)
        segs = analyze_reset_monitor(path)
        self.assertEqual(len(segs), 1)
        seg = segs[0]
        self.assertEqual(seg.boot_id, "C")
        self.assertEqual(seg.sample_count, 3)
        self.assertEqual(seg.max_gpu_watts, 160)
        self.assertEqual(seg.max_gpu_util, 85)
        self.assertTrue(seg.incomplete)
        path.unlink()

    def test_malformed_json(self):
        lines = [
            json.dumps({"boot_id": "D", "time": 20, "gpu": ["38", "170", "90", "1508"]}),
            "{malformed json",
            json.dumps({"boot_id": "D", "time": 22, "gpu": ["39", "180", "95", "1509"]}),
        ]
        path = _write_jsonl(lines)
        segs = analyze_reset_monitor(path)
        self.assertEqual(len(segs), 1)
        seg = segs[0]
        self.assertEqual(seg.boot_id, "D")
        self.assertEqual(seg.sample_count, 2)
        self.assertEqual(seg.max_gpu_watts, 180)
        self.assertTrue(seg.incomplete)
        path.unlink()

