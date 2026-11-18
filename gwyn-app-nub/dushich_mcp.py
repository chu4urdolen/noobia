#!/usr/bin/env python3
"""MCP tools that let Gwyn hand bounded work to local Dushich (adapted from Banshee's)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

import dushich_bridge as bridge


TOOLS = [
    {"name": "dushich_context_status", "description": "Check this Gwyn session's local Dushich handoff context.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "dushich_ask", "description": "Ask the linked local Helper Dushich (free local GPU, no cloud tokens) a question about this Gwyn conversation without creating a coding task or editing files.",
     "inputSchema": {"type": "object", "properties": {
         "question": {"type": "string"}}, "required": ["question"], "additionalProperties": False}},
    {"name": "dushich_start", "description": "Start a small coding task in Dushich's separate local-GPU Codex workspace. Supply a changed file and an independent test. Returns a handoff ID immediately.",
     "inputSchema": {"type": "object", "properties": {
         "task": {"type": "string"},
         "expect": {"type": "array", "items": {"type": "string"}, "description": "Expected paths relative to Dushich's workspace"},
         "test": {"type": "array", "items": {"type": "string"}, "description": "Independent test commands run in Dushich's workspace"},
         "context": {"type": "string", "description": "Selected visible context only; no private reasoning or credentials"},
         "files": {"type": "array", "items": {"type": "string"}, "description": "Selected text files inside /noobia/gwyn-app-nub, sent as reference text"},
     }, "required": ["task", "expect", "test"], "additionalProperties": False}},
    {"name": "dushich_explore", "description": "Ask local Dushich where something is or how it works on Nexus. He checks the forge-db atlas first, explores read-only on the local GPU, records findings in the atlas, and answers. Waits up to 50 seconds, then returns a job ID for dushich_explore_wait.",
     "inputSchema": {"type": "object", "properties": {"question": {"type": "string"}},
                     "required": ["question"], "additionalProperties": False}},
    {"name": "dushich_explore_wait", "description": "Wait up to 50 seconds more for a dushich_explore job and return its answer when finished.",
     "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}},
                     "required": ["id"], "additionalProperties": False}},
    {"name": "dushich_status", "description": "Check a Gwyn handoff's status.",
     "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}},
                     "required": ["id"], "additionalProperties": False}},
    {"name": "dushich_report", "description": "Read Dushich's final reply and independent verification.",
     "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}},
                     "required": ["id"], "additionalProperties": False}},
    {"name": "dushich_wait", "description": "Wait up to 50 seconds for Dushich and return the report when finished.",
     "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}},
                     "required": ["id"], "additionalProperties": False}},
]


def session() -> str:
    return bridge.require_session(os.environ.get("NOOBIA_GWYN_SESSION"))


def owned(run_id: str) -> dict:
    current = bridge.state(run_id)
    if current.get("session_id") != session():
        raise ValueError("Handoff belongs to another Gwyn session")
    return current


def call(name: str, args: dict) -> str:
    current_session = session()
    if name == "dushich_context_status":
        return json.dumps({"session_id": current_session,
                           "handoffs": len(bridge.jobs(current_session)),
                           "model": "qwen3.8:27b via local Ollama"})
    if name == "dushich_ask":
        question = args.get('question')
        if not isinstance(question, str) or not question.strip() or len(question.encode()) > 8000:
            raise ValueError('question must contain up to 8 KB of text')
        conversation_id, _ = bridge.conversation_context(current_session, summarize=False)
        if not conversation_id:
            raise ValueError('Gwyn conversation ID is unavailable')
        process = subprocess.run(['/usr/bin/python3',
                                  '/noobia/gwyn-app-nub/gwyn_helper.py', 'ask',
                                  '--conversation-id', conversation_id,
                                  '--question', question], capture_output=True, text=True,
                                 timeout=400, check=False)
        if process.returncode:
            raise ValueError(process.stderr.strip() or 'Could not ask Helper Dushich')
        return process.stdout.strip()
    if name in {"dushich_explore", "dushich_explore_wait"}:
        if name == "dushich_explore":
            question = args.get("question")
            if not isinstance(question, str) or not question.strip():
                raise ValueError("question is required")
            command = ["/usr/local/bin/dushich-explore", "ask", question, "--by", "Gwyn", "--timeout", "50"]
        else:
            if not isinstance(args.get("id"), str):
                raise ValueError("id is required")
            command = ["/usr/local/bin/dushich-explore", "wait", args["id"], "--timeout", "50"]
        process = subprocess.run(command, capture_output=True, text=True, timeout=90, check=False)
        output = process.stdout.strip() or process.stderr.strip()
        if process.returncode == 2:
            raise ValueError(output)
        if ": running" in output or ": queued" in output:
            output += "\nCall dushich_explore_wait with this job ID."
        return output
    if name == "dushich_start":
        task, expect, tests = args.get("task"), args.get("expect"), args.get("test")
        context, files = args.get("context", ""), args.get("files", [])
        if not isinstance(task, str) or not isinstance(expect, list) or not isinstance(tests, list):
            raise ValueError("task, expect, and test are required")
        if not isinstance(context, str) or not isinstance(files, list) or not all(isinstance(x, str) for x in files):
            raise ValueError("context and files must contain text")
        return bridge.start(current_session, task, expect, tests, context, files)
    if name in {"dushich_status", "dushich_report", "dushich_wait"}:
        run_id = args.get("id")
        if not isinstance(run_id, str):
            raise ValueError("id is required")
        current = owned(run_id)
        if name == "dushich_status":
            return json.dumps(current)
        if name == "dushich_report":
            return bridge.report(run_id)
        for _ in range(50):
            current = owned(run_id)
            if current["status"] in {"done", "needs_gwyn"}:
                return bridge.report(run_id)
            time.sleep(1)
        return "Still running; call dushich_wait again."
    raise ValueError("Unknown tool")


def send(message: dict) -> None:
    sys.stdout.write(json.dumps(message, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def main() -> None:
    for line in sys.stdin:
        message = None
        try:
            message = json.loads(line)
            if "id" not in message:
                continue
            method = message.get("method")
            if method == "initialize":
                result = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}},
                          "serverInfo": {"name": "noobia-gwyn-dushich", "version": "1.0.0"}}
            elif method == "tools/list":
                result = {"tools": TOOLS}
            elif method == "tools/call":
                params = message.get("params") or {}
                try:
                    value = call(params.get("name", ""), params.get("arguments") or {})
                    result = {"content": [{"type": "text", "text": value}], "isError": False}
                except (OSError, ValueError, KeyError) as exc:
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


if __name__ == "__main__":
    main()
