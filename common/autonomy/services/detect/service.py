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

# Raw Bayer frames from Lynx's CAMSV camera (Gwyn, 2026-11-22). Lynx has no
# numpy/PIL, so she posts the raw frame here; decoding, the 270 degree
# upright rotation and gray-world white balance reuse the proven C1 code.
BAYER_SIZES = {(1600, 1200), (3264, 2448)}
_C1 = None


def _c1():
    """Import lynx_camera_c1_wrapper lazily (it pulls in PIL/numpy)."""
    global _C1
    if _C1 is None:
        import os
        import sys
        from pathlib import Path
        cam = Path(os.environ.get("NOOBIA", "/noobia")) / "lynx" / "tools" / "camera"
        tools = cam.parent
        for p in (str(cam), str(tools)):
            if p not in sys.path:
                sys.path.insert(0, p)
        import lynx_camera_c1_wrapper as c1  # noqa: E402
        _C1 = c1
    return _C1


VISION_URL = "http://127.0.0.1:5051/analyze"
DARK_MEAN = 60.0      # 0..255; Lynx's raw sensors have a fixed exposure and no AE
DARK_MIN_CONF = 0.70  # scored labels in brightened (dark) frames must be at least this sure


def brighten_if_dark(png: bytes) -> bytes:
    """Levels stretch + gamma lift for dark frames (evening rooms); bright frames untouched.

    Lynx's CAMSV path has no automatic exposure (camera-control ioctls crash
    her kernel), so at night a frame can average 1/255. Stretching the 1..99.5
    percentiles and lifting the mean toward ~0.4 lets the detectors see."""
    import io
    import numpy as np
    from PIL import Image
    img = Image.open(io.BytesIO(png)).convert("RGB")
    arr = np.asarray(img).astype(np.float32)
    if arr.mean() >= DARK_MEAN:
        return png
    lo, hi = np.percentile(arr, 1.0), np.percentile(arr, 99.5)
    arr = np.clip((arr - lo) / max(hi - lo, 1.0), 0.0, 1.0)
    mean = max(float(arr.mean()), 1e-3)
    gamma = min(max(np.log(0.4) / np.log(mean), 0.15), 1.0) if mean < 0.4 else 1.0
    arr = (arr ** gamma) * 255.0
    out = io.BytesIO()
    Image.fromarray(arr.astype(np.uint8)).save(out, format="PNG")
    return out.getvalue()


def _strong(image: bytes, timeout: float = 45.0) -> tuple[dict | None, str]:
    """(result, note) from nexus_vision; (None, why) if it is down or slow."""
    import urllib.request
    try:
        req = urllib.request.Request(VISION_URL, data=image, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = json.loads(r.read())
        return body, "ok " + json.dumps(body.get("ms", {}))
    except Exception as exc:  # noqa: BLE001 - fall back to YOLOv8n alone
        return None, f"unavailable: {type(exc).__name__}"


def detect_bayer(detector, raw: bytes, width: int, height: int) -> tuple[int, dict]:
    """(HTTP status, body) for one raw RGGB frame. Never an empty success on failure."""
    import time
    if (width, height) not in BAYER_SIZES:
        return 400, {"error": f"unsupported size {width}x{height}; allowed: 1600x1200, 3264x2448"}
    if len(raw) != width * height:
        return 400, {"error": f"expected {width * height} bytes for {width}x{height}, got {len(raw)}"}
    c1 = _c1()
    t0 = time.monotonic()
    try:
        lifted = c1.lift_bayer_to_png(raw, width=width, height=height)
        png = brighten_if_dark(lifted)
        was_dark = png is not lifted
        variants = c1.get_detection_frame_variants(png)
    except Exception as exc:  # undecodable: say so
        return 422, {"error": f"Bayer decode failed: {type(exc).__name__}: {exc}"}
    t1 = time.monotonic()
    # Strong models (YOLO11x + Florence-2, nexus_vision :5051) on the upright,
    # white-balanced frame, in parallel with the fast YOLOv8n variants below.
    import concurrent.futures
    upright = next((b for n, b in variants if n == "upright_wb"), png)
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    strong_future = pool.submit(_strong, upright)
    best: dict[str, float] = {}
    for _name, image in variants:
        for obj in detector.detect_raw(image) or []:
            label = c1.normalize_coco_label(str(obj.get("label", "unknown")))
            conf = float(obj.get("confidence", 0.0))
            if conf > best.get(label, -1.0):
                best[label] = conf
    strong, strong_note = strong_future.result()
    pool.shutdown(wait=False)
    caption = ""
    if strong:
        for obj in strong.get("objects", []):
            lb = c1.normalize_coco_label(str(obj.get("label", "unknown")))
            conf = float(obj.get("confidence", 0.0))
            if conf > best.get(lb, -1.0):
                best[lb] = conf
        caption = str(strong.get("caption", ""))[:300]
    t2 = time.monotonic()
    if was_dark:
        # A brightened night frame is mostly amplified noise: only very sure
        # labels count (0.55 produced "kite" for a person at a desk).
        best = {k: v for k, v in best.items() if v >= DARK_MIN_CONF or abs(v - 0.5) < 1e-6}
    objects = [{"label": k, "confidence": round(v, 4)}
               for k, v in sorted(best.items(), key=lambda kv: -kv[1])]
    return 200, {"objects": objects, "variants": len(variants), "caption": caption, "dark": was_dark,
                 "strong_models": strong_note,
                 "model_loaded": bool(getattr(detector, "model_loaded", False)),
                 "decode_ms": int((t1 - t0) * 1000), "detect_ms": int((t2 - t1) * 1000)}


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

    def _json(self, code: int, body: dict) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode("utf-8"))

    def do_POST(self):
        if self.path.startswith("/detect_bayer"):
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query)
            try:
                width = int(q.get("w", ["1600"])[0])
                height = int(q.get("h", ["1200"])[0])
            except ValueError:
                self._json(400, {"error": "w and h must be integers"})
                return
            length = int(self.headers.get("Content-Length", 0))
            if length <= 0 or length > 10 * 1024 * 1024:
                self._json(400, {"error": "invalid content length"})
                return
            raw = self.rfile.read(length)
            code, body = detect_bayer(self.detector, raw, width, height)
            self._json(code, body)
            return
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
