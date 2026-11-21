#!/usr/bin/env python3
"""Aigel's intake service (PLAN A1, contract section 5).

A host's harness POSTs each unexplained chunk to
``POST /api/v1/chunk``; Aigel's decision **is the HTTP reply** -
she never opens a connection to a host. The reply is the strict
decision JSON (decision, message, patterns, priority_rules, note),
bounded to 64 KiB.

Authentication: per-host HMAC-SHA256 over the raw body
(``X-Noobia-Signature``, hex) or a Bearer token, from the private
host registry (never in Git, ``aigel/private/intake_hosts.json``).
A host that configures no credential is accepted - the documented
LAN-only risk of contract C4. Unknown host or bad credential is a
401, which the client treats as final (no retry storm).

Bounded: request body 256 KiB, 200 lines, 512 bytes per line,
response 64 KiB. Inspectable: every request, decision, and refusal
is written to the ``noobia-aigel`` view. Host liveness: Aigel
remembers the last chunk per host and marks a host ``silent`` when
nothing arrives for its ``silence_s`` (her first nursing duty,
contract liveness note) - exposed read-only on ``GET /api/v1/status``.

A4 (the "People" channel) rides the same service: ``GET /`` is her
web page (host status, recent chunks and decisions, a chat box),
``GET /api/v1/status`` is the data behind it, and ``POST /api/v1/chat``
is a bounded, logged chat turn. See ``aigel_web.py``.

Runs on the Noobia LAN; the privileged port 112 is an admin step in
an install session (A4, IS-3). Until then it runs on any port:

    python3 aigel/service/aigel_intake.py --port 8112 --hosts aigel/private/intake_hosts.json
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:  # package import (aigel.service.aigel_intake)
    from .aigel_log import ViewLogger
    from .aigel_think import AigelThinker
    from .aigel_web import AigelWeb
except ImportError:  # direct script use from aigel/service/
    from aigel_log import ViewLogger
    from aigel_think import AigelThinker
    from aigel_web import AigelWeb

NOOBIA = os.environ.get("NOOBIA", "/noobia")
DEFAULT_HOSTS = NOOBIA + "/aigel/private/intake_hosts.json"
DEFAULT_STATE = NOOBIA + "/aigel/private/intake_state.json"

MAX_BODY_BYTES = 262_144     # 256 KiB
MAX_LINES = 200
MAX_LINE_BYTES = 512
MAX_RESPONSE_BYTES = 65_536
DEFAULT_SILENCE_S = 1800

RECENT_PER_HOST = 20        # A4: history kept per host
RECENT_LIMIT = 50           # A4: history returned on the status page


def load_host_registry(path: str | Path) -> dict:
    """Private per-host auth registry: {host: {hmac_secret, bearer, silence_s}}.

    Missing file -> empty registry (nothing is accepted).
    Malformed file -> ValueError; secrets are hex/base strings only.
    """
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ValueError(f"host registry unreadable: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("host registry must be a JSON object")
    out = {}
    for host, entry in data.items():
        if not isinstance(host, str) or not host.isascii() or not (1 <= len(host) <= 32):
            continue
        if not isinstance(entry, dict):
            continue
        clean = {}
        for key in ("hmac_secret", "bearer"):
            v = entry.get(key)
            if isinstance(v, str) and v.strip():
                clean[key] = v.strip()
        s = entry.get("silence_s")
        if isinstance(s, (int, float)) and not isinstance(s, bool) and 60 <= s <= 86_400:
            clean["silence_s"] = int(s)
        out[host] = clean
    return out


class AigelIntake:
    """The decision path: auth -> bounds -> think -> reply. Thread-safe."""

    def __init__(
        self,
        thinker: AigelThinker,
        hosts: dict,
        log: ViewLogger | None = None,
        state_file: str | Path | None = None,
        default_silence_s: int = DEFAULT_SILENCE_S,
        now_fn=time.time,
    ):
        self.thinker = thinker
        self.hosts = hosts
        self.log = log or ViewLogger("noobia-aigel")
        self.state_file = Path(state_file) if state_file else None
        self.default_silence_s = int(default_silence_s)
        self.now_fn = now_fn
        self._lock = threading.Lock()
        self._state: dict = self._load_state()

    # -- liveness state (Aigel's nursing duty) -----------------------------

    def _load_state(self) -> dict:
        if not self.state_file or not self.state_file.exists():
            return {}
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_state(self) -> None:
        if not self.state_file:
            return
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._state, indent=1, sort_keys=True), encoding="utf-8")
            os.replace(tmp, self.state_file)
        except OSError:
            pass  # state persistence is best-effort, never fatal

    def _touch_host(self, host: str, decision: dict,
                    reason: str = "unknown", n_lines: int = 0) -> None:
        with self._lock:
            now = self.now_fn()
            entry = self._state.get(host, {})
            history = entry.get("recent")
            if not isinstance(history, list):
                history = []
            history.append({
                "t": now,
                "reason": str(reason)[:64],
                "lines": int(n_lines),
                "decision": str(decision.get("decision", "quiet")),
                "message": (str(decision["message"])[:500]
                            if decision.get("message") else None),
                "note": str(decision.get("note") or "")[:240],
            })
            self._state[host] = {
                "last_seen": now,
                "last_decision": str(decision.get("decision", "quiet")),
                "chunks": int(entry.get("chunks", 0)) + 1,
                "recent": history[-RECENT_PER_HOST:],
            }
            self._save_state()

    def host_status(self, now: float | None = None) -> dict:
        now = float(now if now is not None else self.now_fn())
        with self._lock:
            hosts = {}
            for host in sorted(set(list(self.hosts) + list(self._state))):
                entry = self._state.get(host, {})
                silence_s = int(self.hosts.get(host, {}).get("silence_s", self.default_silence_s))
                last_seen = entry.get("last_seen")
                hosts[host] = {
                    "last_seen": last_seen,
                    "last_decision": entry.get("last_decision"),
                    "chunks": int(entry.get("chunks", 0)),
                    "silent": (last_seen is None) or (now - float(last_seen) > silence_s),
                }
            return {"now": now, "hosts": hosts}

    # -- authentication -----------------------------------------------------

    def check_auth(self, host: str, raw_body: bytes, headers: dict) -> tuple[bool, str | None]:
        if host not in self.hosts:
            return False, "unknown host"
        entry = self.hosts.get(host, {})
        secret = entry.get("hmac_secret")
        if secret:
            got = headers.get("X-Noobia-Signature")
            want = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
            if not isinstance(got, str) or not hmac.compare_digest(got.strip().lower(), want):
                return False, "bad signature"
            return True, None
        bearer = entry.get("bearer")
        if bearer:
            auth = headers.get("Authorization") or ""
            want = "Bearer " + bearer
            if not hmac.compare_digest(auth, want):
                return False, "bad token"
            return True, None
        return True, None  # no credential configured: documented LAN-only risk

    # -- the chunk ------------------------------------------------------------

    def handle_chunk(self, raw_body: bytes, headers: dict,
                     now: float | None = None) -> tuple[int, dict]:
        now = float(now if now is not None else self.now_fn())
        if len(raw_body) > MAX_BODY_BYTES:
            self.log.write("refused: body over bound host=? bytes=%d" % len(raw_body))
            return 413, {"error": "body too large"}
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self.log.write("refused: not json")
            return 400, {"error": "not json"}
        if not isinstance(payload, dict):
            self.log.write("refused: not an object")
            return 400, {"error": "not an object"}

        host = payload.get("host")
        if not isinstance(host, str) or not host.isascii() or not (1 <= len(host) <= 32):
            self.log.write("refused: missing host")
            return 400, {"error": "missing host"}

        ok, why = self.check_auth(host, raw_body, headers)
        if not ok:
            self.log.write(f"refused: {why} host={host}")
            return 401, {"error": why}

        reason = payload.get("chunk_reason")
        if reason is not None and not (isinstance(reason, str) and len(reason) <= 64):
            self.log.write(f"refused: bad reason host={host}")
            return 400, {"error": "bad chunk_reason"}
        reason = reason if isinstance(reason, str) else "unknown"

        lines = payload.get("lines")
        if not isinstance(lines, list):
            self.log.write(f"refused: lines missing host={host}")
            return 400, {"error": "lines must be a list"}
        if len(lines) > MAX_LINES:
            self.log.write(f"refused: too many lines ({len(lines)}) host={host}")
            return 400, {"error": f"more than {MAX_LINES} lines"}
        for line in lines:
            if not isinstance(line, str) or len(line.encode("utf-8")) > MAX_LINE_BYTES:
                self.log.write(f"refused: bad line host={host}")
                return 400, {"error": "line over bound"}

        self.log.write(f"request host={host} reason={reason} lines={len(lines)} t={now:.0f}")
        decision = self.thinker.decide(host, reason, lines)
        body = json.dumps(decision, ensure_ascii=False).encode("utf-8")
        if len(body) > MAX_RESPONSE_BYTES:
            body = json.dumps({
                "decision": "quiet", "message": None, "patterns": [],
                "priority_rules": [], "note": "reply over bound; nothing delivered",
            }, ensure_ascii=False).encode("utf-8")
            decision = json.loads(body.decode("utf-8"))
        self._touch_host(host, decision, reason=reason, n_lines=len(lines))
        self.log.write(
            f"decision host={host} decision={decision['decision']} "
            f"patterns={len(decision['patterns'])} priority_rules={len(decision['priority_rules'])} "
            f"note={decision['note'][:80]}"
        )
        return 200, decision

    # -- read-only status (A4's data) ----------------------------------------

    def recent_chunks(self, limit: int = RECENT_LIMIT) -> list:
        """The newest chunks and decisions across hosts, newest first."""
        with self._lock:
            out = []
            for host, entry in self._state.items():
                for item in (entry.get("recent") or []):
                    if isinstance(item, dict):
                        out.append({"host": host, **item})
        out.sort(key=lambda c: float(c.get("t") or 0), reverse=True)
        return out[: int(limit)]

    def status_body(self) -> dict:
        body = self.host_status()
        body["recent"] = self.recent_chunks()
        return body


def make_handler(intake: AigelIntake, web: AigelWeb | None = None):
    class Handler(BaseHTTPRequestHandler):
        server_version = "Aigel/0.2"
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # we log to the view, not stderr
            pass

        def _send(self, code: int, obj: dict) -> None:
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_body(self, length: int) -> bytes:
            raw = b""
            while len(raw) < length:
                part = self.rfile.read(length - len(raw))
                if not part:
                    break
                raw += part
            return raw

        def do_POST(self):  # noqa: N802
            path = self.path.split("?")[0]
            if path not in ("/api/v1/chunk", "/api/v1/chat"):
                self._send(404, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                self._send(400, {"error": "bad Content-Length"})
                return
            if length < 0:
                self._send(400, {"error": "bad Content-Length"})
                return
            raw = self._read_body(length)
            if path == "/api/v1/chat":
                if web is None:
                    self._send(404, {"error": "chat not enabled"})
                    return
                code, obj = web.handle_chat(raw, dict(self.headers))
            else:
                code, obj = intake.handle_chunk(raw, dict(self.headers))
            self._send(code, obj)

        def do_GET(self):  # noqa: N802
            path = self.path.split("?")[0]
            if path == "/api/v1/status":
                self._send(200, intake.status_body())
                return
            if path == "/":
                page = web.page() if web is not None else (
                    b"<!doctype html><meta charset='utf-8'>"
                    b"<title>Aigel</title><body style='font-family:sans-serif'>"
                    b"<h1>Aigel</h1><p>The little nurse angel is listening.</p>"
                    b"<p>Status: <code>GET /api/v1/status</code></p></body>"
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(page)))
                self.end_headers()
                self.wfile.write(page)
                return
            self._send(404, {"error": "not found"})

    return Handler


def main() -> int:
    ap = argparse.ArgumentParser(description="Aigel intake service (PLAN A1)")
    ap.add_argument("--bind", default="0.0.0.0",
                    help="LAN service: host harnesses reach Aigel over the "
                         "Noobia network (contract section 5)")
    ap.add_argument("--port", type=int, default=112)
    ap.add_argument("--chat-token", default=os.environ.get("AIGEL_CHAT_TOKEN"),
                    help="optional Bearer token guarding POST /api/v1/chat")
    ap.add_argument("--hosts", default=DEFAULT_HOSTS,
                    help="private per-host auth registry JSON")
    ap.add_argument("--state", default=DEFAULT_STATE,
                    help="host liveness state file")
    ap.add_argument("--view-dir", default=None,
                    help="write view logs to this dir instead of syslog")
    ap.add_argument("--force-file-log", action="store_true",
                    help="never use logger(1); append to view files")
    args = ap.parse_args()

    try:
        hosts = load_host_registry(args.hosts)
    except ValueError as e:
        print(f"aigel: {e}")
        return 2
    thinker = AigelThinker()
    log = ViewLogger("noobia-aigel", file_dir=args.view_dir, force_file=args.force_file_log)
    intake = AigelIntake(thinker, hosts, log=log, state_file=args.state)
    web = AigelWeb(intake, log, chat_token=args.chat_token or None)
    httpd = ThreadingHTTPServer((args.bind, args.port), make_handler(intake, web))
    log.write(f"aigel intake listening on {args.bind}:{args.port} hosts={sorted(hosts)}")
    print(f"aigel: listening on http://{args.bind}:{args.port} ({len(hosts)} registered hosts)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
