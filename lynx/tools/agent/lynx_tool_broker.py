#!/usr/bin/env python3
"""lynx-tool-broker: catalogued root tool calls for the ordinary agent (LNX-73).

Rose's backlog, P1 "Agent privilege isolation" (Gwyn, 2026-11-25).

Lynx's agent reads words from outside (speech she hears, camera captions,
network findings), so it must not run as root. With the broker:

* `lynx-agent` runs as the unprivileged user `lynx-agent` (the worker drops
  privileges with Python's subprocess credentials). It talks to Qwen and
  decides on tool calls.
* This broker runs as root and listens on a Unix socket only that user's
  group can reach. For each request it:
  - checks the caller's real uid from the kernel (SO_PEERCRED);
  - accepts only a tool from the root-owned catalogue directory, whose name
    matches the catalogue rules (no paths, no symlinked scripts);
  - checks the arguments against the tool's JSON schema (no unknown keys,
    required keys present, types and enums respected);
  - runs the tool script exactly as the agent did before (JSON on stdin,
    bounded timeout, no inference keys in the environment);
  - logs tool, caller uid, ok and duration to /var/log/lynx-tool-broker.jsonl
    (never arguments or output).

Protocol: one JSON line in, one JSON line out.
    -> {"tool": "lynx_speech", "args": {"text": "Hello"}, "exclude": ["lynx_codex"]}
    <- {"ok": true, "exit_code": 0, "output": "..."}

    lynx-tool-broker serve [--socket PATH] [--group lynx-agent] [--allow-uid N ...]
"""
from __future__ import annotations

import argparse
import grp
import json
import os
from pathlib import Path
import re
import socket
import struct
import subprocess
import sys
import threading
import time

TOOLS = Path(os.environ.get("LYNX_AGENT_TOOLS", "/usr/local/share/lynx/agent-tools"))
SOCKET = Path(os.environ.get("LYNX_TOOL_BROKER", "/run/lynx-agent/tool-broker.sock"))
LOG = Path(os.environ.get("LYNX_TOOL_BROKER_LOG", "/var/log/lynx-tool-broker.jsonl"))
NAME = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
MAX_REQUEST = 16384
TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool,
         "object": dict, "array": list}


def manifest(name: str, tools: Path = TOOLS):
    """(script, meta) for a catalogued tool, or (None, reason)."""
    if not isinstance(name, str) or not NAME.fullmatch(name):
        return None, "invalid tool name"
    meta_path, script = tools / f"{name}.json", tools / f"{name}.sh"
    if script.is_symlink() or not script.is_file() or not meta_path.is_file():
        return None, "unknown tool"
    try:
        meta = json.loads(meta_path.read_text())
    except (OSError, ValueError):
        return None, "unreadable tool manifest"
    if not isinstance(meta.get("inputSchema") or meta.get("parameters"), dict):
        return None, "tool has no argument schema"
    return (script, meta), None


def check_args(args, schema: dict) -> str | None:
    """None when the arguments fit the schema, else the reason."""
    if not isinstance(args, dict):
        return "arguments must be an object"
    props = schema.get("properties", {}) or {}
    extra = set(args) - set(props)
    if extra:
        return "unknown argument(s): " + ", ".join(sorted(extra))
    missing = [k for k in schema.get("required", []) if k not in args]
    if missing:
        return "missing argument(s): " + ", ".join(missing)
    for key, value in args.items():
        spec = props.get(key) or {}
        want = TYPES.get(spec.get("type"))
        if want is not None and (not isinstance(value, want) or (want is int and isinstance(value, bool))):
            return f"argument {key} must be {spec.get('type')}"
        if "enum" in spec and value not in spec["enum"]:
            return f"argument {key} must be one of {spec['enum']}"
        if isinstance(value, str) and len(value) > 4000:
            return f"argument {key} is too long"
    return None


def run_tool(request: dict, tools: Path = TOOLS, run=subprocess.run) -> dict:
    name, args = request.get("tool"), request.get("args", {})
    exclude = set(request.get("exclude") or [])
    if name in exclude:
        return {"ok": False, "error": "Tool not available for this kind of job"}
    entry, why = manifest(name, tools)
    if entry is None:
        return {"ok": False, "error": why}
    script, meta = entry
    why = check_args(args, meta.get("inputSchema") or meta.get("parameters"))
    if why:
        return {"ok": False, "error": why}
    timeout = min(180, max(1, int(meta.get("timeout", 10))))
    env = {k: v for k, v in os.environ.items()
           if "KEY" not in k.upper() and not k.startswith(("OPENAI_", "NOOBIA_INFERENCE_"))}
    try:
        result = run(["/bin/sh", str(script)], input=json.dumps(args), capture_output=True,
                     text=True, timeout=timeout, env=env, check=False)
        return {"ok": result.returncode == 0, "exit_code": result.returncode,
                "output": (result.stdout + result.stderr)[-8000:]}
    except (OSError, subprocess.TimeoutExpired):
        return {"ok": False, "error": "Tool unavailable or timed out"}


def peer_uid(conn: socket.socket) -> int:
    creds = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    return struct.unpack("3i", creds)[1]


def log(record: dict, path: Path | None = None) -> None:
    path = path or LOG   # read at call time, so a configured LOG is honoured
    try:
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        with os.fdopen(fd, "a") as fh:
            fh.write(json.dumps(record, separators=(",", ":")) + "\n")
    except OSError:
        pass


def handle(conn: socket.socket, allowed_uids: set[int], tools: Path = TOOLS, uid_of=peer_uid) -> None:
    t0 = time.monotonic()
    with conn:
        conn.settimeout(10)
        uid = uid_of(conn)
        data = b""
        while not data.endswith(b"\n") and len(data) <= MAX_REQUEST:
            chunk = conn.recv(4096)
            if not chunk:
                break
            data += chunk
        if uid not in allowed_uids:
            answer, name = {"ok": False, "error": "caller not allowed"}, None
        elif len(data) > MAX_REQUEST:
            answer, name = {"ok": False, "error": "request too large"}, None
        else:
            try:
                request = json.loads(data.decode("utf-8"))
                name = request.get("tool") if isinstance(request, dict) else None
                answer = run_tool(request, tools) if isinstance(request, dict) else \
                    {"ok": False, "error": "request must be an object"}
            except (ValueError, UnicodeDecodeError):
                answer, name = {"ok": False, "error": "request is not JSON"}, None
        conn.settimeout(200)
        conn.sendall((json.dumps(answer) + "\n").encode())
    log({"t": round(time.time(), 3), "uid": uid, "tool": name if isinstance(name, str) else None,
         "ok": answer.get("ok", False), "error": answer.get("error"),
         "ms": int((time.monotonic() - t0) * 1000)})


def call(tool: str, args: dict, exclude=(), path: Path = SOCKET, timeout: float = 200) -> dict:
    """Client side, used by lynx-agent when it runs unprivileged."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        try:
            s.connect(str(path))
            s.sendall((json.dumps({"tool": tool, "args": args, "exclude": sorted(exclude)}) + "\n").encode())
            data = b""
            while not data.endswith(b"\n"):
                chunk = s.recv(65536)
                if not chunk:
                    break
                data += chunk
        except OSError as exc:
            return {"ok": False, "error": f"tool broker unavailable: {type(exc).__name__}"}
    try:
        return json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {"ok": False, "error": "tool broker answered garbage"}


def serve(path: Path, group: str | None, allowed_uids: set[int], tools: Path = TOOLS) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        path.unlink()
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    old = os.umask(0o177)
    try:
        srv.bind(str(path))
    finally:
        os.umask(old)
    if group:
        os.chown(path, 0, grp.getgrnam(group).gr_gid)
        os.chmod(path, 0o660)
    srv.listen(8)
    print(json.dumps({"event": "broker_ready", "socket": str(path), "allowed_uids": sorted(allowed_uids)}),
          flush=True)
    while True:
        conn, _ = srv.accept()
        threading.Thread(target=handle, args=(conn, allowed_uids, tools), daemon=True).start()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve")
    s.add_argument("--socket", type=Path, default=SOCKET)
    s.add_argument("--group", default="lynx-agent")
    s.add_argument("--allow-uid", type=int, action="append", default=[])
    args = ap.parse_args(argv)
    allowed = set(args.allow_uid) or {0}
    if args.group:
        try:
            g = grp.getgrnam(args.group)
            import pwd
            allowed |= {p.pw_uid for p in pwd.getpwall() if p.pw_gid == g.gr_gid or p.pw_name in g.gr_mem}
        except KeyError:
            print(json.dumps({"event": "broker_failed", "error": f"group {args.group} missing"}), flush=True)
            return 2
    serve(args.socket, args.group, allowed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
