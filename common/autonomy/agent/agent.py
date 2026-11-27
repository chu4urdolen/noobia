"""Universal profile-driven autonomy agent for any Noob (NA-82).

Integrates:
- Tool catalog discovery from tool_dir
- Function calling JSON schema mapping
- OpenAI Chat Completions API format (Nexus vLLM/Ollama, local, or cloud)
- Broker dispatch via Unix domain socket with SO_PEERCRED
- SENSE vs CHAT operational modes
- Profile preamble and memory context
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import socket
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Set, Tuple

from common.autonomy.profile import Profile
from common.autonomy.route import BrainRouter

NAME = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")


class AutonomyAgent:
    def __init__(
        self,
        profile: Optional[Profile] = None,
        tool_dir: Optional[Path | str] = None,
        broker_socket: Optional[Path | str] = None,
        router: Optional[BrainRouter] = None,
    ):
        self.profile = profile or Profile.load()
        self.tool_dir = Path(tool_dir or self.profile.tool_dir)
        self.broker_socket = Path(broker_socket) if broker_socket else None
        self.router = router or BrainRouter()

    def load_tools(self, allowed_tools: Optional[Set[str]] = None, excluded_tools: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
        """Discover tools from tool_dir and return OpenAI function tool specs."""
        tools: List[Dict[str, Any]] = []
        if not self.tool_dir.is_dir():
            return tools

        for path in sorted(self.tool_dir.glob("*.json")):
            name = path.stem
            if not NAME.fullmatch(name):
                continue
            if allowed_tools is not None and name not in allowed_tools:
                continue
            if excluded_tools is not None and name in excluded_tools:
                continue
            try:
                spec = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue

            tools.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": spec.get("description", ""),
                    "parameters": spec.get("inputSchema", {}),
                }
            })
        return tools

    def call_broker(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch tool call through the privileged broker socket."""
        if not self.broker_socket or not self.broker_socket.exists():
            return {"ok": False, "error": "broker socket unavailable"}

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(60.0)
        try:
            sock.connect(str(self.broker_socket))
            req = json.dumps({"tool": tool_name, "args": args}) + "\n"
            sock.sendall(req.encode("utf-8"))
            raw = sock.recv(16384)
            if not raw:
                return {"ok": False, "error": "empty broker response"}
            return json.loads(raw.decode("utf-8", errors="replace").strip())
        except Exception as exc:
            return {"ok": False, "error": f"broker call failed: {exc}"}
        finally:
            sock.close()

    def build_system_prompt(self) -> str:
        base = f"You are {self.profile.name}, an autonomous Noob of Noobia.\n"
        if "preamble" in self.profile.paths and Path(self.profile.paths["preamble"]).exists():
            try:
                base += Path(self.profile.paths["preamble"]).read_text(encoding="utf-8").strip() + "\n"
            except OSError:
                pass
        return base.strip()

    def run_turn(self, prompt: str, allowed_tools: Optional[Set[str]] = None) -> Tuple[bool, str]:
        """Execute one conversational / sensory turn."""
        tools = self.load_tools(allowed_tools=allowed_tools)
        system_prompt = self.build_system_prompt()

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        backend = self.router.select_backend()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {backend.api_key}",
        }
        body: Dict[str, Any] = {
            "model": backend.model,
            "messages": messages,
        }
        if tools:
            body["tools"] = tools

        req = urllib.request.Request(
            f"{backend.url}/v1/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            return False, f"Inference failed: {exc}"

        choice = result.get("choices", [{}])[0]
        msg = choice.get("message", {})
        content = msg.get("content", "") or ""
        tool_calls = msg.get("tool_calls", [])

        # Execute tool calls if any
        tool_outputs = []
        for tc in tool_calls:
            fn = tc.get("function", {})
            tname = fn.get("name")
            try:
                targs = json.loads(fn.get("arguments", "{}"))
            except ValueError:
                targs = {}
            res = self.call_broker(tname, targs)
            tool_outputs.append(f"[{tname}: {res.get('output', res.get('error', 'ok'))}]")

        final_text = content
        if tool_outputs:
            if final_text:
                final_text += " "
            final_text += " ".join(tool_outputs)

        return True, final_text.strip()
