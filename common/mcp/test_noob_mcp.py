#!/usr/bin/env python3
"""Comprehensive test suite for Noobia MCP server and manifest converter."""

import json
from pathlib import Path
import tempfile
import unittest

from manifest_converter import load_manifest_tools, manifest_to_mcp_tool
from noob_mcp import NoobMCPServer
from mcp_client import InProcessMCPServerAdapter, MCPClient


class TestManifestConverter(unittest.TestCase):
    def test_manifest_to_mcp_tool_valid(self):
        meta = {
            "description": "Read Lynx sensor status",
            "protocol": "json-stdin",
            "timeout": 5,
            "parameters": {
                "type": "object",
                "properties": {
                    "sensor_type": {"type": "string", "enum": ["accel", "gyro"]}
                },
                "required": ["sensor_type"],
                "additionalProperties": False,
            },
        }
        tool = manifest_to_mcp_tool("lynx_sensor", meta)
        self.assertEqual(tool["name"], "lynx_sensor")
        self.assertEqual(tool["description"], "Read Lynx sensor status")
        self.assertEqual(tool["inputSchema"]["type"], "object")
        self.assertIn("sensor_type", tool["inputSchema"]["properties"])
        self.assertEqual(tool["inputSchema"]["required"], ["sensor_type"])

    def test_manifest_invalid_protocol(self):
        with self.assertRaises(ValueError):
            manifest_to_mcp_tool("bad_tool", {"protocol": "custom-binary"})

    def test_manifest_invalid_name(self):
        with self.assertRaises(ValueError):
            manifest_to_mcp_tool("123bad_name!", {"protocol": "json-stdin"})

    def test_load_manifest_tools(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            (p / "my_tool.json").write_text(
                json.dumps({
                    "description": "Custom test tool",
                    "protocol": "json-stdin",
                    "parameters": {"type": "object", "properties": {}},
                })
            )
            (p / "my_tool.sh").write_text("#!/bin/sh\necho ok\n")

            tools = load_manifest_tools(p)
            self.assertIn("my_tool", tools)
            script, meta, mcp_def = tools["my_tool"]
            self.assertEqual(mcp_def["name"], "my_tool")
            self.assertEqual(mcp_def["description"], "Custom test tool")


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
        self.assertTrue(len(tools) > 10)
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
            # Note: Lynx is currently reachable on the test network!
            self.assertFalse(is_err)
            self.assertIn("OK", text)


if __name__ == "__main__":
    unittest.main()
