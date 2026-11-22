#!/usr/bin/env python3
"""Nexus Voice Service for Lynx.

Synthesizes speech using Piper on Nexus (en_US-kristin-medium) and returns
volume-attenuated 48kHz stereo WAV for Lynx's speaker hardware safety.
Reuses the Rose distributed voice design and authenticates via Lynx's key.
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

HOST = "192.168.100.106"
PORT = 115
KEY_FILE = Path("/noobia/lynx/private/lynx_voice.key")
PIPER_BIN = "/home/aria/piper/bin/piper-tts/piper"
DEFAULT_VOICE = "/home/aria/piper/voices/en_US/kristin/medium/en_US-kristin-medium.onnx"

def load_key() -> str:
    if not KEY_FILE.is_file():
        raise RuntimeError(f"Missing voice key at {KEY_FILE}")
    return KEY_FILE.read_text().strip()

class LynxVoiceHandler(BaseHTTPRequestHandler):
    key = ""

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "service": "lynx_voice"}).encode())
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if self.path != "/api/v1/tts":
            self.send_response(404)
            self.end_headers()
            return

        # Check authorization
        auth = self.headers.get("Authorization", "")
        token = auth[7:].strip() if auth.startswith("Bearer ") else auth.strip()
        if token != self.key:
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error": "unauthorized"}')
            return

        length = int(self.headers.get("Content-Length", 0))
        if length > 65536:
            self.send_response(413)
            self.end_headers()
            return

        body = self.rfile.read(length)
        try:
            req = json.loads(body.decode("utf-8"))
            text = req.get("text", "").strip()
            voice_path = req.get("voice", DEFAULT_VOICE)
        except Exception:
            self.send_response(400)
            self.end_headers()
            return

        if not text:
            self.send_response(400)
            self.end_headers()
            return

        try:
            with tempfile.TemporaryDirectory(prefix="lynx-piper-") as tmp:
                raw_wav = Path(tmp) / "raw.wav"
                safe_wav = Path(tmp) / "safe.wav"

                # 1. Synthesize via Piper
                syn = subprocess.run([
                    PIPER_BIN,
                    "--model", voice_path,
                    "--output_file", str(raw_wav)
                ], input=text.encode("utf-8"), capture_output=True, timeout=8)
                if syn.returncode != 0 or not raw_wav.is_file():
                    raise RuntimeError(f"Piper error: {syn.stderr.decode()}")

                # 2. Resample & scale volume to 0.08 with +500 cents pitch (1.33484) via rubberband
                sox = subprocess.run([
                    "ffmpeg", "-y", "-i", str(raw_wav),
                    "-af", "volume=0.08,rubberband=pitch=1.33484",
                    "-ar", "48000", "-ac", "2",
                    str(safe_wav)
                ], capture_output=True, timeout=8)
                if sox.returncode != 0 or not safe_wav.is_file():
                    raise RuntimeError(f"Volume scaling error: {sox.stderr.decode()}")

                wav_data = safe_wav.read_bytes()

            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(wav_data)))
            self.end_headers()
            self.wfile.write(wav_data)
        except Exception as exc:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(exc)}).encode())

    def log_message(self, format, *args):
        # Concise logging
        sys.stderr.write(f"[lynx_voice] {format % args}\n")

def main():
    key = load_key()
    LynxVoiceHandler.key = key
    server = HTTPServer((HOST, PORT), LynxVoiceHandler)
    sys.stderr.write(f"[lynx_voice] Serving Piper TTS on {HOST}:{PORT}\n")
    server.serve_forever()

if __name__ == "__main__":
    main()
