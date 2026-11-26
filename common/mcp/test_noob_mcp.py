#!/usr/bin/env python3
"""Comprehensive test suite for Noobia MCP server and client (native MCP by default)."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

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
        self.assertIn("argus_collect_day", tool_names)
        self.assertIn("argus_daily_ledger", tool_names)
        self.assertIn("argus_find_events", tool_names)
        self.assertIn("argus_forge_notes_on", tool_names)
        self.assertIn("argus_source_record", tool_names)

    def test_argus_tool_routes_to_bounded_client(self):
        with patch("noob_mcp.handle_argus", return_value='{"job_id":"x"}') as route:
            text, is_error = self.server.call_tool("argus_job_result", {"job_id": "a" * 32})
        self.assertFalse(is_error)
        self.assertEqual(json.loads(text), {"job_id": "x"})
        route.assert_called_once_with("job-result", {"job_id": "a" * 32})

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


class TestLynxRemoteRouting(unittest.TestCase):
    def test_extract_remote_command(self):
        with tempfile.NamedTemporaryFile("w+", delete=False) as f:
            f.write("#!/bin/sh\n# Test wrapper\nexec /usr/bin/python3 /usr/local/bin/lynx-test-tool arg1\n")
            f.flush()
            tmp_path = Path(f.name)
        try:
            cmd = NoobMCPServer._extract_remote_command(tmp_path)
            self.assertEqual(cmd, "/usr/bin/python3 /usr/local/bin/lynx-test-tool arg1")
        finally:
            tmp_path.unlink()

    def test_extract_remote_command_without_exec(self):
        with tempfile.NamedTemporaryFile("w+", delete=False) as f:
            f.write("/usr/bin/python3 /usr/local/bin/lynx-direct-tool\n")
            f.flush()
            tmp_path = Path(f.name)
        try:
            cmd = NoobMCPServer._extract_remote_command(tmp_path)
            self.assertEqual(cmd, "/usr/bin/python3 /usr/local/bin/lynx-direct-tool")
        finally:
            tmp_path.unlink()

    def test_lynx_remote_script_handler_success(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            sh_file = p / "lynx_dummy.sh"
            sh_file.write_text("#!/bin/sh\nexec /usr/bin/python3 /usr/local/bin/lynx-dummy\n")
            meta = {"name": "lynx_dummy", "timeout": 5}
            handler = NoobMCPServer._make_lynx_remote_script_handler(sh_file, meta)

            mock_res = MagicMock()
            mock_res.returncode = 0
            mock_res.stdout = '{"status": "ready", "temperature": 32.5}\n'
            mock_res.stderr = ""

            with patch("subprocess.run", return_value=mock_res) as mock_run:
                out = handler({})
                parsed = json.loads(out)
                self.assertTrue(parsed["ok"])
                self.assertEqual(parsed["result"]["status"], "ready")
                self.assertEqual(parsed["result"]["temperature"], 32.5)

                # Verify ssh command was called with port 2222
                mock_run.assert_called_once()
                args, kwargs = mock_run.call_args
                cmd_argv = args[0]
                self.assertEqual(cmd_argv[0], "ssh")
                self.assertIn("-p", cmd_argv)
                idx = cmd_argv.index("-p")
                self.assertEqual(cmd_argv[idx + 1], "2222")
                self.assertIn("/usr/bin/python3 /usr/local/bin/lynx-dummy", cmd_argv)

    def test_lynx_remote_script_handler_error_exit(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            sh_file = p / "lynx_dummy.sh"
            sh_file.write_text("#!/bin/sh\nexec /usr/bin/python3 /usr/local/bin/lynx-dummy\n")
            handler = NoobMCPServer._make_lynx_remote_script_handler(sh_file, {})

            mock_res = MagicMock()
            mock_res.returncode = 1
            mock_res.stdout = ""
            mock_res.stderr = "Permission denied"

            with patch("subprocess.run", return_value=mock_res):
                out = handler({})
                parsed = json.loads(out)
                self.assertFalse(parsed["ok"])
                self.assertEqual(parsed["exit_code"], 1)
                self.assertIn("Permission denied", parsed["error"])

    def test_lynx_remote_script_handler_timeout(self):
        import subprocess
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            sh_file = p / "lynx_dummy.sh"
            sh_file.write_text("#!/bin/sh\nexec /usr/bin/python3 /usr/local/bin/lynx-dummy\n")
            handler = NoobMCPServer._make_lynx_remote_script_handler(sh_file, {"timeout": 3})

            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="ssh", timeout=3)):
                out = handler({})
                parsed = json.loads(out)
                self.assertFalse(parsed["ok"])
                self.assertIn("timed out", parsed["error"])

    def test_live_lynx_platform_status(self):
        server = NoobMCPServer()
        self.assertIn("lynx_platform_status", server.tools)
        text, is_err = server.call_tool("lynx_platform_status", {})
        self.assertFalse(is_err)
        data = json.loads(text)
        self.assertTrue(data.get("ok"), f"Tool call failed: {text}")
        result = data.get("result", {})
        self.assertIn("battery", result)
        self.assertIn("thermal", result)
        self.assertIn("wifi", result)


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
