"""HTTP daemon for Nexus Object Detection Service (port 5050)."""

from __future__ import annotations

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import logging
from typing import Any
try:
    from .detector import ObjectDetector
except (ImportError, ValueError):
    from detector import ObjectDetector

logger = logging.getLogger("nexus-detect")


class DetectRequestHandler(BaseHTTPRequestHandler):
    detector: ObjectDetector = ObjectDetector()

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            resp = {
                "status": "ok" if getattr(self.detector, "model_loaded", False) else "degraded",
                "model": bool(getattr(self.detector, "model_loaded", False)),
                "engine": self.detector.engine,
                "tpu": self.detector.tpu_available,
            }
            self.wfile.write(json.dumps(resp).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path.startswith("/detect"):
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length <= 0 or content_length > 10 * 1024 * 1024:  # 10 MB limit
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'{"error": "invalid content length"}')
                return

            # Read frame strictly in memory
            frame_bytes = self.rfile.read(content_length)
            objects = self.detector.detect_raw(frame_bytes)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            resp = {"objects": objects}
            self.wfile.write(json.dumps(resp).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def make_server(host: str = "0.0.0.0", port: int = 5050) -> HTTPServer:
    server = HTTPServer((host, port), DetectRequestHandler)
    return server


if __name__ == "__main__":
    server = make_server("0.0.0.0", 5050)
    print("Nexus detect service running on :5050")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
