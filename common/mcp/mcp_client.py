#!/usr/bin/env python3
"""Standard MCP Client for Noobia agents and scripts.

Connects to any Model Context Protocol server (stdio subprocess or in-process)
and provides standard list_tools() and call_tool() interfaces.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple


class MCPClient:
    """Client for communicating with an MCP server over stdio."""

    def __init__(self, command: List[str], cwd: Optional[str | Path] = None):
        self.command = command
        self.cwd = str(cwd) if cwd else None
        self.process: Optional[subprocess.Popen] = None
        self._next_id = 1
        self.server_info: Dict[str, Any] = {}
        self.capabilities: Dict[str, Any] = {}

    def start(self) -> None:
        """Start the MCP server subprocess."""
        if self.process is not None:
            return
        self.process = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=self.cwd,
            bufsize=1,
        )

    def close(self) -> None:
        """Terminate the MCP server subprocess."""
        if self.process is None:
            return
        try:
            if self.process.stdin:
                self.process.stdin.close()
            if self.process.stdout:
                self.process.stdout.close()
            if self.process.stderr:
                self.process.stderr.close()
            self.process.terminate()
            self.process.wait(timeout=2)
        except Exception:
            self.process.kill()
        finally:
            self.process = None

    def __enter__(self) -> MCPClient:
        self.start()
        self.initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def _send_request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if self.process is None or self.process.poll() is not None:
            self.start()

        msg_id = self._next_id
        self._next_id += 1

        payload: Dict[str, Any] = {"jsonrpc": "2.0", "id": msg_id, "method": method}
        if params is not None:
            payload["params"] = params

        wire = json.dumps(payload, separators=(",", ":")) + "\n"
        assert self.process and self.process.stdin
        self.process.stdin.write(wire)
        self.process.stdin.flush()

        # Read response line
        assert self.process.stdout
        line = self.process.stdout.readline()
        if not line:
            stderr = self.process.stderr.read() if self.process.stderr else ""
            raise RuntimeError(f"MCP server exited unexpectedly. Stderr: {stderr.strip()}")

        try:
            res = json.loads(line)
        except Exception as exc:
            raise RuntimeError(f"Invalid JSON from MCP server: {line.strip()}") from exc

        if "error" in res:
            err = res["error"]
            raise RuntimeError(f"MCP Error ({err.get('code')}): {err.get('message')}")

        return res.get("result", {})

    def initialize(self) -> Dict[str, Any]:
        """Perform MCP initialize handshake."""
        result = self._send_request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "noobia-agent-mcp-client", "version": "1.0.0"},
            },
        )
        self.server_info = result.get("serverInfo", {})
        self.capabilities = result.get("capabilities", {})
        return result

    def list_tools(self) -> List[Dict[str, Any]]:
        """Query server for available tools."""
        result = self._send_request("tools/list")
        return result.get("tools", [])

    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Tuple[str, bool]:
        """Invoke an MCP tool by name. Returns (text_content, is_error)."""
        result = self._send_request("tools/call", {"name": name, "arguments": arguments or {}})
        content = result.get("content", [])
        is_error = bool(result.get("isError", False))

        text_parts = [part["text"] for part in content if part.get("type") == "text"]
        return "\n".join(text_parts), is_error


class InProcessMCPServerAdapter:
    """Fast in-process adapter that wraps NoobMCPServer directly without subprocessing."""

    def __init__(self, server=None):
        if server is None:
            from noob_mcp import NoobMCPServer  # type: ignore
            self.server = NoobMCPServer()
        else:
            self.server = server

    def list_tools(self) -> List[Dict[str, Any]]:
        return self.server.list_tools()

    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Tuple[str, bool]:
        return self.server.call_tool(name, arguments or {})

    def openai_tool_definitions(self) -> List[Dict[str, Any]]:
        """Convert MCP tools into OpenAI function calling format for LLMs."""
        definitions = []
        for tool in self.list_tools():
            definitions.append({
                "type": "function",
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["inputSchema"],
                "strict": True,
            })
        return definitions
