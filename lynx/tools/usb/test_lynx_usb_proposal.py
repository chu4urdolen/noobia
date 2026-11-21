#!/usr/bin/env python3
"""Unit tests for lynx_usb_serial_status catalog proposal."""

import json
from pathlib import Path
import unittest

PROPOSAL_DIR = Path(__file__).resolve().parent / "catalog_proposal"
LOCAL_CALLS_DIR = Path(__file__).resolve().parent.parent / "local_calls"


class TestLynxUsbProposal(unittest.TestCase):
    def test_schema_valid(self):
        schema_path = PROPOSAL_DIR / "lynx_usb_serial_status.json"
        self.assertTrue(schema_path.exists())
        data = json.loads(schema_path.read_text())
        self.assertEqual(data["name"], "lynx_usb_serial_status")
        self.assertIn("description", data)
        self.assertEqual(data["inputSchema"]["type"], "object")
        self.assertEqual(data["inputSchema"]["required"], [])
        self.assertFalse(data["inputSchema"]["additionalProperties"])
        self.assertEqual(data["timeout"], 8)

    def test_wrapper_valid(self):
        wrapper_path = PROPOSAL_DIR / "lynx_usb_serial_status.sh"
        self.assertTrue(wrapper_path.exists())
        lines = wrapper_path.read_text().splitlines()
        self.assertTrue(len(lines) >= 2)
        self.assertEqual(lines[0], "#!/bin/sh")
        self.assertIn("lynx-usb-serial-status", wrapper_path.read_text())

    def test_manifest_entry_valid(self):
        manifest_path = PROPOSAL_DIR / "manifest_entry.json"
        self.assertTrue(manifest_path.exists())
        entry = json.loads(manifest_path.read_text())
        self.assertEqual(entry["name"], "lynx_usb_serial_status")
        self.assertEqual(entry["effect"], "read_only")
        self.assertEqual(entry["group"], "hardware")
        self.assertEqual(entry["status_source"], "hardware")
        self.assertEqual(entry["component"], "usb")
        self.assertFalse(entry["reports_component_status"])
        self.assertEqual(entry["timeout_s"], 8)

    def test_coverage_entry_valid(self):
        cov_path = PROPOSAL_DIR / "coverage_entry.json"
        self.assertTrue(cov_path.exists())
        cov = json.loads(cov_path.read_text())
        self.assertEqual(cov["effect"], "read_only")
        self.assertEqual(cov["coverage_role"], "read_tool")
        self.assertEqual(cov["target_component"], "hardware/usb")
        self.assertEqual(cov["tools_map_tuple"][0], "read_only")
        self.assertEqual(cov["tools_map_tuple"][1], "hardware")
        self.assertEqual(cov["tools_map_tuple"][2], ["hardware", "usb"])
        self.assertFalse(cov["tools_map_tuple"][3])

    def test_local_calls_boundary_enforced(self):
        """Verify tool is NOT added to local_calls until Aria approves."""
        json_in_local = LOCAL_CALLS_DIR / "lynx_usb_serial_status.json"
        sh_in_local = LOCAL_CALLS_DIR / "lynx_usb_serial_status.sh"
        self.assertFalse(json_in_local.exists(), "Tool must not be added to local_calls without Aria approval")
        self.assertFalse(sh_in_local.exists(), "Tool must not be added to local_calls without Aria approval")


if __name__ == "__main__":
    unittest.main()
