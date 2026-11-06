#!/usr/bin/env python3
"""Authenticated LAN inference endpoint backed by Nexus's loopback Ollama."""

from __future__ import annotations

import argparse
from http.client import HTTPConnection, HTTPException
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
from pathlib import Path
import threading
import time
from urllib.parse import urlsplit


MODEL_ALIAS = "gpt-oss-20b"
OLLAMA_MODEL = "gpt-oss:20b"
KEY_FILE = Path("/home/aria/.config/noobia/gpt-oss-20b.api-key")
ALLOWED_POST = {"/v1/chat/completions", "/v1/responses", "/v1/embeddings"}
MAX_BODY = 16 * 1024 * 1024


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"  # Close-delimited bodies also support streamed replies.
    server_version = "NoobiaInference/1"

    def json_reply(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def authorized(self) -> bool:
        supplied = self.headers.get("Authorization", "")
        expected = "Bearer " + KEY_FILE.read_text(encoding="utf-8").strip()
        return hmac.compare_digest(supplied, expected)

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path == "/health":
            try:
                connection = HTTPConnection("127.0.0.1", 11434, timeout=3)
                connection.request("GET", "/api/version")
                response = connection.getresponse()
                healthy = response.status == 200
                response.read()
                connection.close()
            except (OSError, HTTPException):
                healthy = False
            self.json_reply(200 if healthy else 503,
                            {"status": "ok" if healthy else "unavailable"})
            return
        if not self.authorized():
            self.json_reply(401, {"error": "unauthorized"})
            return
        if path == "/v1/models":
            self.json_reply(200, {"object": "list", "data": [
                {"id": MODEL_ALIAS, "object": "model", "created": 0, "owned_by": "noobia"}
            ]})
        elif path == f"/v1/models/{MODEL_ALIAS}":
            self.json_reply(200, {"id": MODEL_ALIAS, "object": "model",
                                  "created": 0, "owned_by": "noobia"})
        else:
            self.json_reply(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if not self.authorized():
            self.json_reply(401, {"error": "unauthorized"})
            return
        if path not in ALLOWED_POST:
            self.json_reply(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self.json_reply(411, {"error": "Content-Length required"})
            return
        if length < 0 or length > MAX_BODY:
            self.json_reply(413, {"error": "request too large"})
            return
        try:
            data = json.loads(self.rfile.read(length))
        except (ValueError, UnicodeDecodeError):
            self.json_reply(400, {"error": "invalid JSON"})
            return
        if not isinstance(data, dict) or data.get("model") not in {MODEL_ALIAS, OLLAMA_MODEL}:
            self.json_reply(400, {"error": "unknown model"})
            return
        data["model"] = OLLAMA_MODEL
        body = json.dumps(data, separators=(",", ":")).encode("utf-8")
        connection = HTTPConnection("127.0.0.1", 11434, timeout=300)
        headers_sent = False
        try:
            connection.request("POST", path, body=body,
                               headers={"Content-Type": "application/json"})
            response = connection.getresponse()
            self.send_response(response.status)
            self.send_header("Content-Type", response.getheader("Content-Type", "application/json"))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            headers_sent = True
            while chunk := response.read1(65536):
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass  # Client disconnected during a streamed response.
        except (OSError, HTTPException):
            if not headers_sent and not self.wfile.closed:
                try:
                    self.json_reply(502, {"error": "Ollama unavailable"})
                except (BrokenPipeError, ConnectionResetError):
                    pass
        finally:
            connection.close()


def warm_model() -> None:
    """Load the one local model before advertising the LAN endpoint."""
    body = json.dumps({"model": OLLAMA_MODEL, "prompt": "", "stream": False,
                       "keep_alive": -1, "options": {"num_predict": 0}}).encode("utf-8")
    for _ in range(30):
        connection = HTTPConnection("127.0.0.1", 11434, timeout=120)
        try:
            connection.request("POST", "/api/generate", body=body,
                               headers={"Content-Type": "application/json"})
            response = connection.getresponse()
            response.read()
            if response.status == 200:
                return
        except (OSError, HTTPException):
            pass
        finally:
            connection.close()
        time.sleep(1)
    raise RuntimeError("Ollama model could not be warmed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--loopback-only", action="store_true")
    args = parser.parse_args()
    warm_model()
    hosts = ["127.0.0.1"] if args.loopback_only else ["127.0.0.1", "192.168.100.106"]
    servers = [ThreadingHTTPServer((host, args.port), Handler) for host in hosts]
    for server in servers[1:]:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    servers[0].serve_forever()


if __name__ == "__main__":
    main()
