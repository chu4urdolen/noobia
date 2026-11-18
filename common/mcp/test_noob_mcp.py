#!/usr/bin/env python3
"""Comprehensive test suite for Noobia MCP server and client (native MCP by default)."""

import json
from pathlib import Path
import tempfile
import unittest

from noob_mcp import NoobMCPServer, load_native_mcp_tools
from mcp_client import InProcessMCPServerAdapter, MCPClient


class TestNativeMCPManifests(unittest.TestCase):
    def test_load_native_mcp_tools(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            (p / "lynx_custom_sensor.json").write_text(
                json.dumps({
                    "name": "lynx_custom_sensor",
                    "description": "Read Lynx custom sensor",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "samples": {"type": "integer", "minimum": 1, "maximum": 10}
                        },
                        "required": ["samples"],
                        "additionalProperties": False,
                    },
                    "timeout": 5,
                })
            )
            (p / "lynx_custom_sensor.sh").write_text("#!/bin/sh\necho ok\n")

            tools = load_native_mcp_tools(p)
            self.assertIn("lynx_custom_sensor", tools)
            script, mcp_def = tools["lynx_custom_sensor"]
            self.assertEqual(mcp_def["name"], "lynx_custom_sensor")
            self.assertEqual(mcp_def["description"], "Read Lynx custom sensor")
            self.assertEqual(mcp_def["inputSchema"]["type"], "object")
            self.assertIn("samples", mcp_def["inputSchema"]["properties"])


class TestNoobMCPServer(unittest.TestCase):
    def setUp(self):
        self.server = NoobMCPServer(manifest_dirs=[])

    def test_initialize(self):
        req = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        resp = self.server.handle_request(req)
        self.assertEqual(resp["jsonrpc"], "2.0")
        self.assertEqual(resp["id"], 1)
        self.assertIn("protocolVersion", resp["result"])
        self.assertEqual(resp["result"]["serverInfo"]["name"], "noobia-mcp")

    def test_tools_list(self):
        req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        resp = self.server.handle_request(req)
        tools = resp["result"]["tools"]
        tool_names = [t["name"] for t in tools]
        self.assertIn("lynx_ping", tool_names)
        self.assertIn("lynx_battery", tool_names)
        self.assertIn("lynx_motion_read", tool_names)
        self.assertIn("iris_ping", tool_names)
        self.assertIn("iris_camera_capture", tool_names)

    def test_unknown_method(self):
        req = {"jsonrpc": "2.0", "id": 3, "method": "nonexistent/method", "params": {}}
        resp = self.server.handle_request(req)
        self.assertIn("error", resp)
        self.assertEqual(resp["error"]["code"], -32601)

    def test_call_tool_not_found(self):
        req = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "ghost_tool", "arguments": {}},
        }
        resp = self.server.handle_request(req)
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("not found", resp["result"]["content"][0]["text"])

    def test_in_process_adapter(self):
        adapter = InProcessMCPServerAdapter(self.server)
        tools = adapter.list_tools()
        self.assertTrue(len(tools) >= 20)
        defs = adapter.openai_tool_definitions()
        self.assertEqual(len(defs), len(tools))
        self.assertEqual(defs[0]["type"], "function")
        self.assertIn("parameters", defs[0])


class TestMCPClientSubprocess(unittest.TestCase):
    def test_client_subprocess_roundtrip(self):
        server_path = Path(__file__).resolve().parent / "noob_mcp.py"
        client = MCPClient(["python3", str(server_path)])
        with client:
            tools = client.list_tools()
            self.assertTrue(len(tools) >= 20)
            text, is_err = client.call_tool("lynx_ping")
            self.assertFalse(is_err)
            self.assertIn("OK", text)


if __name__ == "__main__":
    unittest.main()
