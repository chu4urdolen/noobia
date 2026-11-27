"""Universal tool broker: catalogued root tool calls for unprivileged agents (NA-81).

Generic isolation broker running as root and serving requests from unprivileged
agents over a Unix domain socket with kernel SO_PEERCRED validation.
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
from typing import Any, Dict, List, Optional, Set, Tuple

NAME = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
MAX_REQUEST = 16384
TYPES = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "object": dict,
    "array": list,
}


def manifest(name: str, tools: Path) -> Tuple[Optional[Path], Optional[str]]:
    """(script, meta) for a catalogued tool, or (None, reason)."""
    if not isinstance(name, str) or not NAME.fullmatch(name):
        return None, "invalid tool name"
    meta_path = tools / f"{name}.json"
    script = tools / f"{name}.sh"
    if script.is_symlink() or not script.is_file() or not meta_path.is_file():
        return None, "unknown tool"
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, "corrupt manifest"
    if not isinstance(data, dict) or data.get("name") != name:
        return None, "mismatched manifest"
    return script, data


def validate_args(schema: Dict[str, Any], args: Any) -> Optional[str]:
    """Return error string if args violates JSON schema, or None if valid."""
    if not isinstance(args, dict):
        return "arguments must be a JSON object"
    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    additional = schema.get("additionalProperties", False)

    for k in required:
        if k not in args:
            return f"missing required argument: {k}"

    for k, v in args.items():
        if k not in props and not additional:
            return f"unknown argument: {k}"
        if k in props:
            expected_type = props[k].get("type")
            if expected_type in TYPES:
                valid_cls = TYPES[expected_type]
                # In Python bool is subclass of int; reject bool if integer expected
                if expected_type in ("integer", "number") and isinstance(v, bool):
                    return f"argument {k} must be {expected_type}, not boolean"
                if not isinstance(v, valid_cls):
                    return f"argument {k} must be {expected_type}"
            if "enum" in props[k] and v not in props[k]["enum"]:
                return f"argument {k} value not in allowed enum"

    return None


def dispatch_tool(script: Path, args: Dict[str, Any], timeout: float = 30.0) -> Tuple[bool, int, str]:
    """Execute tool script with JSON on stdin, stripped environment, and timeout."""
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": "/tmp",
        "NOOBIA": os.environ.get("NOOBIA", "/noobia"),
    }
    raw_in = json.dumps(args)
    start = time.monotonic()
    try:
        proc = subprocess.run(
            [str(script)],
            input=raw_in,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        ok = (proc.returncode == 0)
        output = proc.stdout.strip() or proc.stderr.strip()
        return ok, proc.returncode, output
    except subprocess.TimeoutExpired:
        return False, 124, "tool execution timed out"
    except Exception as exc:
        return False, 127, f"execution error: {exc}"


class ToolBroker:
    def __init__(self, tool_dir: Path | str, socket_path: Path | str, log_path: Optional[Path | str] = None, allow_uids: Optional[Set[int]] = None):
        self.tools = Path(tool_dir)
        self.socket_path = Path(socket_path)
        self.log_path = Path(log_path) if log_path else None
        self.allow_uids = set(allow_uids) if allow_uids is not None else None
        self._server_sock: Optional[socket.socket] = None
        self._running = False

    def log(self, tool: str, uid: int, ok: bool, duration_ms: float) -> None:
        if not self.log_path:
            return
        entry = {
            "ts": time.time(),
            "tool": tool,
            "caller_uid": uid,
            "ok": ok,
            "duration_ms": round(duration_ms, 2),
        }
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            pass

    def handle_client(self, conn: socket.socket) -> None:
        try:
            # Kernel SO_PEERCRED check
            creds = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
            pid, uid, gid = struct.unpack("3i", creds)
            if self.allow_uids is not None and uid not in self.allow_uids and uid != 0:
                conn.sendall(json.dumps({"ok": False, "error": f"caller uid {uid} not allowed"}).encode("utf-8") + b"\n")
                return

            raw = conn.recv(MAX_REQUEST)
            if not raw:
                return
            data = json.loads(raw.decode("utf-8", errors="replace").strip())
            tool_name = data.get("tool")
            args = data.get("args", {})

            script, meta_or_err = manifest(tool_name, self.tools)
            if not script:
                conn.sendall(json.dumps({"ok": False, "error": meta_or_err}).encode("utf-8") + b"\n")
                return

            schema = meta_or_err.get("inputSchema", {})
            err = validate_args(schema, args)
            if err:
                conn.sendall(json.dumps({"ok": False, "error": f"invalid arguments: {err}"}).encode("utf-8") + b"\n")
                return

            timeout = min(float(meta_or_err.get("timeout", 30)), 180.0)
            start = time.monotonic()
            ok, code, output = dispatch_tool(script, args, timeout=timeout)
            duration_ms = (time.monotonic() - start) * 1000.0

            self.log(tool_name, uid, ok, duration_ms)
            conn.sendall(json.dumps({"ok": ok, "exit_code": code, "output": output}).encode("utf-8") + b"\n")
        except Exception as exc:
            try:
                conn.sendall(json.dumps({"ok": False, "error": str(exc)}).encode("utf-8") + b"\n")
            except OSError:
                pass
        finally:
            conn.close()

    def serve_forever(self) -> None:
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        if self.socket_path.exists():
            self.socket_path.unlink()

        self._server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server_sock.bind(str(self.socket_path))
        # Group permissions
        try:
            self.socket_path.chmod(0o660)
        except OSError:
            pass
        self._server_sock.listen(16)
        self._running = True

        while self._running:
            try:
                conn, _ = self._server_sock.accept()
                t = threading.Thread(target=self.handle_client, args=(conn,), daemon=True)
                t.start()
            except OSError:
                break

    def stop(self) -> None:
        self._running = False
        if self._server_sock:
            self._server_sock.close()
        if self.socket_path.exists():
            self.socket_path.unlink()
