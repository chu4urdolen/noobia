#!/usr/bin/env python3
"""nexus_vision: strong object detection and captions on Nexus's CPU (port 5051).

Tom, 2026-11-23: "find some really cool model ... run both models
simultaneously, we got tons of CPU and RAM". Two models run in parallel on
every image, CPU only (the RTX 5090 stays reserved for Qwen):

- YOLO11x (Ultralytics, AGPL-3.0): accurate boxes for the 80 COCO classes.
- Florence-2-large (Microsoft, MIT): open-vocabulary objects (<OD>) and a
  detailed caption (<DETAILED_CAPTION>).

    POST /analyze   body: one PNG/JPEG image
      -> {"objects": [{"label", "confidence", "source"}...],
          "caption": "...", "ms": {"yolo": n, "florence": n}, "errors": {...}}
    GET  /health    -> {"status": "ok"|"loading"|"degraded", "models": {...}}

Florence-2 gives no scores; its objects carry confidence 0.5 and
source "florence". One model failing never hides the other's result.
Run: common/runtime/vision-venv/bin/python service.py [--port 5051]
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import io
import json
import os
from pathlib import Path
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

NOOBIA = Path(os.environ.get("NOOBIA", "/noobia"))
MODELS = NOOBIA / "common" / "runtime" / "models"
YOLO_WEIGHTS = MODELS / "yolo11x.pt"
FLORENCE_ID = os.environ.get("NEXUS_FLORENCE_MODEL", "microsoft/Florence-2-large")
MAX_BODY = 20 * 1024 * 1024
YOLO_MIN_CONF = 0.35

_state = {"yolo": None, "florence": None, "processor": None, "errors": {}, "loading": True}
_lock = threading.Lock()      # torch CPU inference: one image at a time per model


def label(text: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", str(text).strip().lower()).strip("_")[:32] or "unknown"


def load_models() -> None:
    os.environ.setdefault("HF_HOME", str(MODELS / "hf"))
    try:
        import torch
        torch.set_num_threads(max(2, (os.cpu_count() or 4) // 2))
    except Exception as exc:  # noqa: BLE001
        _state["errors"]["torch"] = repr(exc)
    try:
        from ultralytics import YOLO
        _state["yolo"] = YOLO(str(YOLO_WEIGHTS) if YOLO_WEIGHTS.exists() else "yolo11x.pt")
    except Exception as exc:  # noqa: BLE001
        _state["errors"]["yolo"] = repr(exc)
    try:
        from unittest import mock
        from transformers import AutoModelForCausalLM, AutoProcessor
        from transformers.dynamic_module_utils import get_imports

        def no_flash_attn(path):   # Florence-2's remote code lists flash_attn; CPU has none
            return [i for i in get_imports(path) if i != "flash_attn"]
        with mock.patch("transformers.dynamic_module_utils.get_imports", no_flash_attn):
            _state["florence"] = AutoModelForCausalLM.from_pretrained(
                FLORENCE_ID, trust_remote_code=True, attn_implementation="eager").eval()
            _state["processor"] = AutoProcessor.from_pretrained(FLORENCE_ID, trust_remote_code=True)
    except Exception as exc:  # noqa: BLE001
        _state["errors"]["florence"] = repr(exc)
    _state["loading"] = False


def run_yolo(img) -> list[dict]:
    res = _state["yolo"].predict(img, conf=YOLO_MIN_CONF, verbose=False, device="cpu")[0]
    names = res.names
    return [{"label": label(names[int(c)]), "confidence": round(float(p), 4), "source": "yolo11x"}
            for c, p in zip(res.boxes.cls.tolist(), res.boxes.conf.tolist())]


def run_florence(img) -> tuple[list[dict], str]:
    import torch
    model, proc = _state["florence"], _state["processor"]
    out = {}
    for task in ("<OD>", "<DETAILED_CAPTION>"):
        inputs = proc(text=task, images=img, return_tensors="pt")
        with torch.no_grad():
            ids = model.generate(input_ids=inputs["input_ids"], pixel_values=inputs["pixel_values"],
                                 max_new_tokens=256, num_beams=3, do_sample=False)
        text = proc.batch_decode(ids, skip_special_tokens=False)[0]
        out[task] = proc.post_process_generation(text, task=task, image_size=img.size)[task]
    objects = [{"label": label(n), "confidence": 0.5, "source": "florence2"}
               for n in dict.fromkeys(out["<OD>"].get("labels", []))]
    return objects, str(out["<DETAILED_CAPTION>"]).strip()


def analyze(image_bytes: bytes) -> dict:
    from PIL import Image
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    result = {"objects": [], "caption": "", "ms": {}, "errors": {}}

    def timed(name, fn):
        t = time.monotonic()
        try:
            return fn(img)
        except Exception as exc:  # noqa: BLE001
            result["errors"][name] = f"{type(exc).__name__}: {str(exc)[:160]}"
            return None
        finally:
            result["ms"][name] = int((time.monotonic() - t) * 1000)

    jobs = {}
    with ThreadPoolExecutor(max_workers=2) as pool:      # both models at the same time
        if _state["yolo"] is not None:
            jobs["yolo"] = pool.submit(timed, "yolo", run_yolo)
        if _state["florence"] is not None:
            jobs["florence"] = pool.submit(timed, "florence", run_florence)
    yolo = jobs["yolo"].result() if "yolo" in jobs else None
    flo = jobs["florence"].result() if "florence" in jobs else None
    best: dict[str, dict] = {}
    for o in (yolo or []) + ((flo or ([], ""))[0]):
        if o["label"] not in best or o["confidence"] > best[o["label"]]["confidence"]:
            best[o["label"]] = o
    result["objects"] = sorted(best.values(), key=lambda o: -o["confidence"])
    if flo:
        result["caption"] = flo[1]
    return result


class Handler(BaseHTTPRequestHandler):
    def _json(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            models = {"yolo11x": _state["yolo"] is not None, "florence2": _state["florence"] is not None}
            status = "loading" if _state["loading"] else ("ok" if all(models.values()) else "degraded")
            self._json(200, {"status": status, "models": models, "errors": _state["errors"]})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        if self.path != "/analyze":
            self._json(404, {"error": "not found"})
            return
        n = int(self.headers.get("Content-Length", 0))
        if n <= 0 or n > MAX_BODY:
            self._json(400, {"error": "invalid content length"})
            return
        body = self.rfile.read(n)
        if _state["loading"]:
            self._json(503, {"error": "models still loading"})
            return
        try:
            with _lock:
                self._json(200, analyze(body))
        except Exception as exc:  # noqa: BLE001
            self._json(422, {"error": f"{type(exc).__name__}: {str(exc)[:160]}"})

    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5051)
    ap.add_argument("--bind", default="127.0.0.1")   # only the detect service calls it
    args = ap.parse_args()
    threading.Thread(target=load_models, daemon=True).start()
    ThreadingHTTPServer((args.bind, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
