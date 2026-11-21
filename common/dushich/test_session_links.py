#!/usr/bin/env python3
"""Unit tests for persistent session links and hooks."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import session_links
import bridge


class TestSessionLinks(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.orig_db = session_links.DB_PATH
        session_links.DB_PATH = Path(self.temp_dir) / "test_session_links.db"

    def tearDown(self):
        session_links.DB_PATH = self.orig_db
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_set_and_get_link(self):
        session_links.set_link("banshee", "sess-1234", "conv-5678")
        self.assertEqual(session_links.get_conversation("banshee", "sess-1234"), "conv-5678")
        self.assertEqual(session_links.get_launcher_session("banshee", "conv-5678"), "sess-1234")
        self.assertEqual(session_links.get_latest_conversation("banshee"), "conv-5678")
        self.assertTrue(session_links.is_conversation_active_or_linked("banshee", "conv-5678"))
        self.assertFalse(session_links.is_conversation_active_or_linked("banshee", "unknown"))

    def test_switch_conversation(self):
        session_links.set_link("banshee", "sess-1", "conv-1")
        self.assertEqual(session_links.get_conversation("banshee", "sess-1"), "conv-1")
        # Resume or start new
        session_links.set_link("banshee", "sess-1", "conv-2")
        self.assertEqual(session_links.get_conversation("banshee", "sess-1"), "conv-2")
        self.assertEqual(session_links.get_latest_conversation("banshee"), "conv-2")

    def test_hook_antigravity_payload(self):
        old_env = os.environ.get("NOOBIA_BANSHEE_SESSION")
        os.environ["NOOBIA_BANSHEE_SESSION"] = "sess-agy"
        try:
            payload = json.dumps({"conversationId": "conv-agy-999", "hookEventName": "SessionStart"})
            sys.stdin = io.StringIO(payload)
            ret = session_links.handle_hook("banshee")
            self.assertEqual(ret, 0)
            self.assertEqual(session_links.get_conversation("banshee", "sess-agy"), "conv-agy-999")
        finally:
            if old_env is None:
                os.environ.pop("NOOBIA_BANSHEE_SESSION", None)
            else:
                os.environ["NOOBIA_BANSHEE_SESSION"] = old_env

    def test_hook_claude_payload(self):
        old_env = os.environ.get("NOOBIA_GWYN_SESSION")
        os.environ["NOOBIA_GWYN_SESSION"] = "sess-gwyn"
        try:
            payload = json.dumps({"session_id": "conv-gwyn-888"})
            sys.stdin = io.StringIO(payload)
            ret = session_links.handle_hook("gwyn")
            self.assertEqual(ret, 0)
            self.assertEqual(session_links.get_conversation("gwyn", "sess-gwyn"), "conv-gwyn-888")
        finally:
            if old_env is None:
                os.environ.pop("NOOBIA_GWYN_SESSION", None)
            else:
                os.environ["NOOBIA_GWYN_SESSION"] = old_env

    def test_bridge_conversation_id_integration(self):
        bridge.use("banshee")
        session_links.set_link("banshee", "97b6b70d-e4d8-44b8-88d6-8ad20b88710c", "conv-test-live")
        cid = bridge.conversation_id("97b6b70d-e4d8-44b8-88d6-8ad20b88710c")
        self.assertEqual(cid, "conv-test-live")


if __name__ == "__main__":
    unittest.main()
