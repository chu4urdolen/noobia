"""Boundary and protocol checks for the shared Dushich bridge and MCP server."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import bridge
import mcp

bridge.use("banshee")


SESSION_A = "11111111-1111-1111-1111-111111111111"
SESSION_B = "22222222-2222-2222-2222-222222222222"
RUN_ID = "20261114T120000Z-1234abcd"


class BridgeBoundaryTests(unittest.TestCase):
    def test_rejects_missing_session_and_external_context_file(self):
        with self.assertRaises(ValueError):
            bridge.require_session(None)
        with self.assertRaises(ValueError):
            bridge.selected_context("", ["/etc/passwd"])

    def test_mcp_does_not_read_another_sessions_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            job = root / RUN_ID
            job.mkdir()
            (job / "state.json").write_text(json.dumps({"session_id": SESSION_A, "status": "done"}))
            (job / "result.txt").write_text("private result")
            backend = mcp.Shared("banshee")
            with patch.object(bridge, "ROOT", root), patch.dict(os.environ, {"NOOBIA_BANSHEE_SESSION": SESSION_B}):
                with self.assertRaisesRegex(ValueError, "another Banshee session"):
                    mcp.call(backend, "dushich_report", {"id": RUN_ID})

    def test_mcp_stdio_lists_tools_and_binds_session(self):
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "dushich_context_status", "arguments": {}}},
        ]
        environment = dict(os.environ, NOOBIA_BANSHEE_SESSION=SESSION_A)
        result = subprocess.run(
            [sys.executable, str(Path(mcp.__file__)), "--agent", "banshee"],
            input="\n".join(json.dumps(item) for item in requests) + "\n",
            capture_output=True, text=True, env=environment, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        replies = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(replies), 3)
        names = {tool["name"] for tool in replies[1]["result"]["tools"]}
        self.assertTrue({"dushich_ask", "dushich_start", "dushich_explore"} <= names)
        context = json.loads(replies[2]["result"]["content"][0]["text"])
        self.assertEqual(context["session_id"], SESSION_A)


class AgentParityTests(unittest.TestCase):
    def test_every_agent_gets_the_same_tools(self):
        names = {tuple(t["name"] for t in mcp.tools(name)) for name in ("Aria", "Banshee", "Gwyn")}
        self.assertEqual(len(names), 1)

    def test_agent_table_drives_paths_and_status(self):
        bridge.use("gwyn")
        try:
            self.assertEqual(bridge.ROOT, bridge.agents.NOOBIA / "gwyn-app-nub/private/task-runs")
            self.assertTrue(bridge.finished("needs_gwyn"))
            self.assertFalse(bridge.finished("needs_banshee"))
        finally:
            bridge.use("banshee")


if __name__ == "__main__":
    unittest.main()
