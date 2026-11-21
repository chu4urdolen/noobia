#!/usr/bin/env python3
"""The `dushich` MCP server: every cloud agent's tools for local Dushich.

    mcp.py --agent aria|banshee|gwyn

Every agent gets the same tools:

    dushich_context_status  this session's handoff context
    dushich_ask             ask the Helper Dushich thread linked to this conversation
    dushich_start           start a verified coding handoff (returns an ID)
    dushich_status / dushich_wait / dushich_report
    dushich_explore / dushich_explore_wait   "where is / how does" on Nexus

Banshee's and Gwyn's handoffs run through bridge.py. Aria's run through her own
Codex bridge (aria/dushich-bridge), which this server drives by its command line.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

import agents

NOOBIA = agents.NOOBIA
EXPLORE = NOOBIA / "common/tools/dushich_explore.py"
UUID = re.compile(r"^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$")
TEXT = {"type": "string"}
ID_ONLY = {"type": "object", "properties": {"id": TEXT}, "required": ["id"], "additionalProperties": False}


def tools(name: str) -> list[dict]:
    return [
        {"name": "dushich_context_status", "description": f"Check this {name} session's local Dushich handoff context.",
         "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
        {"name": "dushich_ask", "description": f"Ask the linked local Helper Dushich (local GPU, no cloud tokens) a question about this {name} conversation without creating a coding task or editing files.",
         "inputSchema": {"type": "object", "properties": {"question": TEXT}, "required": ["question"], "additionalProperties": False}},
        {"name": "dushich_start", "description": "Start a small coding task in Dushich's separate local-GPU Codex workspace. Supply an expected changed file and an independent test. Returns a handoff ID immediately.",
         "inputSchema": {"type": "object", "properties": {
             "task": TEXT,
             "expect": {"type": "array", "items": TEXT, "description": "Expected paths relative to Dushich's workspace"},
             "test": {"type": "array", "items": TEXT, "description": "Independent test commands run in Dushich's workspace"},
             "context": {"type": "string", "description": "Selected visible context only; no private reasoning or credentials"},
             "files": {"type": "array", "items": TEXT, "description": f"Selected text files from {name}'s directory, sent as reference text"},
         }, "required": ["task", "expect", "test"], "additionalProperties": False}},
        {"name": "dushich_status", "description": f"Check a {name} handoff's status.", "inputSchema": ID_ONLY},
        {"name": "dushich_report", "description": "Read Dushich's final reply and independent verification.", "inputSchema": ID_ONLY},
        {"name": "dushich_wait", "description": "Wait up to 50 seconds for Dushich and return the report when finished.", "inputSchema": ID_ONLY},
        {"name": "dushich_explore", "description": "Ask local Dushich where something is or how it works on Nexus. He checks the forge-db atlas first, explores read-only on the local GPU, records findings in the atlas, and answers. Waits up to 50 seconds, then returns a job ID for dushich_explore_wait.",
         "inputSchema": {"type": "object", "properties": {"question": TEXT}, "required": ["question"], "additionalProperties": False}},
        {"name": "dushich_explore_wait", "description": "Wait up to 50 seconds more for a dushich_explore job and return its answer when finished.", "inputSchema": ID_ONLY},
    ]


def run(command: list[str], timeout: int) -> str:
    process = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    if process.returncode:
        raise ValueError(process.stderr.strip() or process.stdout.strip() or "Dushich command failed")
    return process.stdout.strip()


def text(args: dict, key: str, limit: int = 8000) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value.strip() or len(value.encode()) > limit:
        raise ValueError(f"{key} must contain up to {limit // 1000} KB of text")
    return value


def explore(name: str, args: dict, tool: str) -> str:
    if tool == "dushich_explore":
        command = [sys.executable, str(EXPLORE), "ask", text(args, "question"), "--by", name, "--timeout", "50"]
    else:
        command = [sys.executable, str(EXPLORE), "wait", text(args, "id", 100), "--timeout", "50"]
    process = subprocess.run(command, capture_output=True, text=True, timeout=90, check=False)
    output = process.stdout.strip() or process.stderr.strip()
    if process.returncode == 2:
        raise ValueError(output)
    if ": running" in output or ": queued" in output:
        output += "\nCall dushich_explore_wait with this job ID."
    return output


class Shared:
    """Banshee and Gwyn: bridge.py, a session ID from the launcher, a helper module."""

    def __init__(self, key: str):
        import bridge
        bridge.use(key)
        self.bridge, self.agent = bridge, agents.get(key)
        self.name = self.agent.name

    def session(self) -> str:
        s = os.environ.get(self.agent.session_env)
        if not s:
            import session_links
            latest_conv = session_links.get_latest_conversation(self.agent.key)
            if latest_conv:
                s = session_links.get_launcher_session(self.agent.key, latest_conv)
        return self.bridge.require_session(s)

    def owned(self, run_id: str) -> dict:
        current = self.bridge.state(run_id)
        if current.get("session_id") != self.session():
            raise ValueError(f"Handoff belongs to another {self.name} session")
        return current

    def context_status(self, args: dict) -> str:
        session = self.session()
        return json.dumps({"session_id": session, "handoffs": len(self.bridge.jobs(session)),
                           "model": "qwen3.8:27b via local Ollama"})

    def ask(self, question: str) -> str:
        conversation = self.bridge.conversation_id(self.session())
        if not conversation:
            raise ValueError(f"{self.name} conversation ID is unavailable")
        helper = Path(__file__).resolve().parent / f"{self.agent.helper}.py"
        return run([sys.executable, str(helper), "ask", "--conversation-id", conversation,
                    "--question", question], self.agent.ask_timeout)

    def start(self, args: dict) -> str:
        return self.bridge.start(self.session(), args["task"], args["expect"], args["test"],
                                 args.get("context", ""), args.get("files", []))

    def status(self, run_id: str) -> dict:
        return self.owned(run_id)

    def report(self, run_id: str) -> str:
        self.owned(run_id)
        return self.bridge.report(run_id)

    def finished(self, status: str) -> bool:
        return self.bridge.finished(status)


class Aria:
    """Aria: her Codex bridge CLI; the session ID is inferred from Codex's state."""

    name = "Aria"
    BRIDGE = str(agents.ARIA / "dushich-bridge")
    TALK = str(agents.ARIA / "talk-to-dushich")
    SESSIONS = agents.HOME / ".codex/sessions"

    def __init__(self, session: str | None = None):
        self.current = session if session and UUID.fullmatch(session) else None

    def session(self) -> str:
        self.current = self.current or self.infer()
        if not self.current:
            raise ValueError("Aria session ID unavailable; start Aria with noobia-codex")
        return self.current

    def infer(self) -> str | None:
        inherited = os.environ.get("CODEX_SESSION_ID", "")
        if UUID.fullmatch(inherited):
            return inherited
        try:
            locks = sorted((agents.HOME / ".codex/thread-writer-locks").glob("*.lock"),
                           key=lambda p: p.stat().st_mtime, reverse=True)
            for lock in locks:
                if UUID.fullmatch(lock.stem) and list(self.SESSIONS.rglob(f"*{lock.stem}.jsonl")):
                    return lock.stem
        except OSError:
            pass
        candidates = []
        for path in self.SESSIONS.rglob("*.jsonl"):
            try:
                with path.open(encoding="utf-8") as stream:
                    first = json.loads(stream.readline())
                meta = first.get("payload", {})
                if first.get("type") == "session_meta" and meta.get("cwd") == str(NOOBIA) \
                        and UUID.fullmatch(meta.get("id", "")):
                    candidates.append((path.stat().st_mtime, meta["id"]))
            except (OSError, ValueError, KeyError, TypeError):
                continue
        res = max(candidates)[1] if candidates else None
        if res:
            try:
                import session_links
                session_links.set_link("aria", "active", res)
            except Exception:
                pass
        return res

    def context_status(self, args: dict) -> str:
        return run([self.BRIDGE, "context-status", "--session-id", self.session()], 60)

    def ask(self, question: str) -> str:
        return run([self.TALK, "--session-id", self.session(), question], 400)

    def start(self, args: dict) -> str:
        command = [self.BRIDGE, "start", "--session-id", self.session()]
        for item in args["expect"]:
            command += ["--expect", item]
        for item in args["test"]:
            command += ["--test", item]
        for item in args.get("files", []):
            command += ["--include", item]
        context = args.get("context", "")
        if not context:
            return run(command + [args["task"]], 60)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as file:
            file.write(context)
        try:
            return run(command + ["--context-file", file.name, args["task"]], 60)
        finally:
            Path(file.name).unlink(missing_ok=True)

    def status(self, run_id: str) -> dict:
        return json.loads(run([self.BRIDGE, "status", run_id], 30))

    def report(self, run_id: str) -> str:
        return run([self.BRIDGE, "report", run_id], 30)

    def finished(self, status: str) -> bool:
        return status in {"done", "needs_aria"}


def call(backend, name: str, args: dict) -> str:
    if name == "dushich_context_status":
        return backend.context_status(args)
    if name == "dushich_ask":
        return backend.ask(text(args, "question"))
    if name in {"dushich_explore", "dushich_explore_wait"}:
        return explore(backend.name, args, name)
    if name == "dushich_start":
        lists = [args.get(k, []) for k in ("expect", "test", "files")]
        if not isinstance(args.get("task"), str) or not args.get("expect") or not args.get("test") \
                or not all(isinstance(v, list) and all(isinstance(x, str) for x in v) for v in lists) \
                or not isinstance(args.get("context", ""), str):
            raise ValueError("task, expect, and test are required; expect, test, and files are lists of text")
        return backend.start(args)
    if name in {"dushich_status", "dushich_report", "dushich_wait"}:
        run_id = text(args, "id", 100)
        if name == "dushich_status":
            return json.dumps(backend.status(run_id))
        if name == "dushich_report":
            return backend.report(run_id)
        for _ in range(50):
            if backend.finished(backend.status(run_id).get("status", "")):
                return backend.report(run_id)
            time.sleep(1)
        return "Still running; call dushich_wait again."
    raise ValueError("Unknown tool")


def send(message: dict) -> None:
    sys.stdout.write(json.dumps(message, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def serve(backend) -> None:
    for line in sys.stdin:
        message = None
        try:
            message = json.loads(line)
            if "id" not in message:
                continue
            method = message.get("method")
            if method == "initialize":
                result = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}},
                          "serverInfo": {"name": f"noobia-dushich-{backend.name.lower()}", "version": "2.0.0"}}
            elif method == "tools/list":
                result = {"tools": tools(backend.name)}
            elif method == "tools/call":
                params = message.get("params") or {}
                try:
                    value = call(backend, params.get("name", ""), params.get("arguments") or {})
                    result = {"content": [{"type": "text", "text": value}], "isError": False}
                except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
                    result = {"content": [{"type": "text", "text": str(exc)}], "isError": True}
            else:
                send({"jsonrpc": "2.0", "id": message["id"],
                      "error": {"code": -32601, "message": "Method not found"}})
                continue
            send({"jsonrpc": "2.0", "id": message["id"], "result": result})
        except Exception as exc:
            if isinstance(message, dict) and "id" in message:
                send({"jsonrpc": "2.0", "id": message["id"],
                      "error": {"code": -32603, "message": str(exc)}})


def main() -> None:
    parser = argparse.ArgumentParser(description="The dushich MCP server for one cloud agent")
    parser.add_argument("--agent", required=True, choices=["aria", *sorted(agents.AGENTS)])
    parser.add_argument("--session-id", help="Aria only: her Codex session ID, if it cannot be inferred")
    args = parser.parse_args()
    serve(Aria(args.session_id) if args.agent == "aria" else Shared(args.agent))


if __name__ == "__main__":
    main()
