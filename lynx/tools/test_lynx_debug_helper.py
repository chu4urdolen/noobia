"""Unit tests for lynx_debug_helper (Banshee, 2026-11-25)."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import lynx_debug_helper as helper


class TestLynxDebugHelper(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.tmpdir.name)
        helper.RUN_DIR = self.run_dir

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_translate_sense_line(self):
        patterns = [
            {
                "id": "touch-tap",
                "match": {"sense": "touch", "event": "tap"},
                "template": "Someone tapped your screen {count} times.",
                "message": "Someone tapped your screen.",
            },
            {
                "id": "camera-dark",
                "match": {"sense": "camera", "event": "dark"},
                "template": "It is too dark to see much with your {cam} camera.",
                "message": "Too dark to see.",
            },
        ]

        # Matched touch
        raw1 = "NOOBIA P1 touch tap count=3 dur_ms=90 | taps"
        res1 = helper.translate_sense_line(raw1, patterns)
        self.assertEqual(res1, "[touch-tap] Someone tapped your screen 3 times.")

        # Matched camera
        raw2 = "NOOBIA P20 camera dark cam=front | dark"
        res2 = helper.translate_sense_line(raw2, patterns)
        self.assertEqual(res2, "[camera-dark] It is too dark to see much with your front camera.")

        # Unmatched sense line
        raw3 = "NOOBIA P20 body status.sample slider=vibrate | alert slider at vibrate"
        res3 = helper.translate_sense_line(raw3, patterns)
        self.assertIn("[body.status.sample]", res3)
        self.assertIn("alert slider at vibrate", res3)

    def test_write_tools_catalog(self):
        sample_tools = [
            {"name": "tool_a", "sample": "{}", "desc": "Tool A description"},
            {"name": "tool_b", "sample": '{"foo": "bar"}', "desc": "Tool B description"},
        ]
        helper.write_tools_catalog(sample_tools)
        catalog_path = self.run_dir / "debug_tools.txt"
        self.assertTrue(catalog_path.exists())
        content = catalog_path.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(content), 2)
        self.assertEqual(content[0], "tool_a|{}|Tool A description")
        self.assertEqual(content[1], 'tool_b|{"foo": "bar"}|Tool B description')

    def test_run_tool_mock(self):
        tools_map = {
            "mock_tool": {
                "name": "mock_tool",
                "script": "/bin/true",
                "sample": "{}",
                "desc": "mock",
            }
        }
        raw, trans = helper.run_tool("mock_tool", "{}", tools_map)
        self.assertIn("[TOOL: mock_tool] exit=0", raw)
        self.assertIn("[TOOL: mock_tool] OK", trans)

        # Unknown tool
        raw_unk, trans_unk = helper.run_tool("nonexistent", "{}", tools_map)
        self.assertIn("unknown tool", raw_unk)


if __name__ == "__main__":
    unittest.main()
