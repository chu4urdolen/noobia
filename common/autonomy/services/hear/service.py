#!/usr/bin/env python3
"""nexus_hear: what a Noob hears, on Nexus's CPU (port 5052).

Tom, 2026-11-24: give Lynx real hearing (sense plan G1). Two models, CPU only
(the RTX 5090 stays reserved for Qwen):

- AST (MIT/ast-finetuned-audioset, BSD-3): 527 AudioSet sound classes
  (speech, music, knock, laughter, dog, alarm, ...), fast.
- Whisper-small (OpenAI, MIT): speech to text in any language. Runs only
  when AST hears speech, so noise never turns into invented words.

    POST /hear?rate=48000   body: raw signed 16-bit little-endian mono PCM,
                            0.5-15 s (the Noob's mic as it is)
      -> {"sounds": [{"label", "score"}...], "speech": "...", "language": "en",
          "speech_score": 0.0-1.0, "rms": n, "ms": {...}, "errors": {...}}
    GET  /health  -> {"status": "ok"|"loading"|"degraded", "models": {...}}

Privacy: audio lives only in this request's memory; nothing is written to
disk or logged - only labels and text leave the service.
Run: common/runtime/vision-venv/bin/python service.py [--port 5052]
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

NOOBIA = Path(os.environ.get("NOOBIA", "/noobia"))
MODELS = NOOBIA / "common" / "runtime" / "models"
WHISPER_ID = os.environ.get("NEXUS_WHISPER_MODEL", "openai/whisper-small")
AST_ID = os.environ.get("NEXUS_AST_MODEL", "MIT/ast-finetuned-audioset-10-10-0.4593")
RATE = 16000
MIN_S, MAX_S = 0.5, 15.0
TOP_SOUNDS = 5
MIN_SOUND_SCORE = 0.15
SPEECH_GATE = 0.25        # AST "Speech" score needed before Whisper runs
# Whisper's well-known inventions on near-silence; dropped unless speech is clear.
HALLUCINATIONS = {"thank you.", "thanks for watching!", "thank you for watching.",
                  "you", "bye.", ".", "thank you very much."}
# Names Whisper should expect (it heard "Blinks" for "Lynx" without a hint).
NAMES_PROMPT = os.environ.get("NEXUS_HEAR_PROMPT", "Lynx, Tom, Noobia, Gwyn, Aria, Banshee, Dushich, Aigel, Rose, Iris.")
SPEECHY = {"speech", "male speech, man speaking", "female speech, woman speaking",
           "child speech, kid speaking", "conversation", "narration, monologue"}

_state = {"whisper": None, "wproc": None, "ast": None, "aproc": None,
          "errors": {}, "loading": True}
_lock = threading.Lock()      # one clip at a time; CPU inference


def load_models() -> None:
    os.environ.setdefault("HF_HOME", str(MODELS / "hf"))
    try:
        import torch
        # Match the unit's CPUQuota (400%): more threads than CPUs only fight.
        torch.set_num_threads(int(os.environ.get("NEXUS_HEAR_THREADS", "4")))
    except Exception as exc:  # noqa: BLE001
        _state["errors"]["torch"] = repr(exc)
    try:
        from transformers import ASTForAudioClassification, AutoFeatureExtractor
        _state["aproc"] = AutoFeatureExtractor.from_pretrained(AST_ID)
        _state["ast"] = ASTForAudioClassification.from_pretrained(AST_ID).eval()
    except Exception as exc:  # noqa: BLE001
        _state["errors"]["ast"] = repr(exc)
    try:
        from transformers import WhisperForConditionalGeneration, WhisperProcessor
        _state["wproc"] = WhisperProcessor.from_pretrained(WHISPER_ID)
        _state["whisper"] = WhisperForConditionalGeneration.from_pretrained(WHISPER_ID).eval()
    except Exception as exc:  # noqa: BLE001
        _state["errors"]["whisper"] = repr(exc)
    _state["loading"] = False


def pcm_to_audio(body: bytes, rate: int):
    """float32 mono at 16 kHz from raw S16LE PCM, plus its RMS (int16 scale)."""
    import numpy as np
    from scipy.signal import resample_poly
    if rate not in (8000, 16000, 22050, 24000, 32000, 44100, 48000):
        raise ValueError(f"unsupported rate {rate}")
    pcm = np.frombuffer(body[: len(body) // 2 * 2], dtype="<i2")
    seconds = len(pcm) / rate
    if not MIN_S <= seconds <= MAX_S:
        raise ValueError(f"clip is {seconds:.2f} s; allowed {MIN_S}-{MAX_S} s")
    rms = float(np.sqrt(np.mean(pcm.astype(np.float64) ** 2))) if len(pcm) else 0.0
    audio = pcm.astype(np.float32) / 32768.0
    if rate != RATE:
        from math import gcd
        g = gcd(rate, RATE)
        audio = resample_poly(audio, RATE // g, rate // g).astype(np.float32)
    return audio, rms, seconds


def classify(audio) -> list[dict]:
    import torch
    proc, model = _state["aproc"], _state["ast"]
    inputs = proc(audio, sampling_rate=RATE, return_tensors="pt")
    with torch.no_grad():
        probs = torch.sigmoid(model(**inputs).logits)[0]
    top = torch.topk(probs, 15)
    labels = model.config.id2label
    return [{"label": labels[int(i)], "score": round(float(p), 3)}
            for p, i in zip(top.values.tolist(), top.indices.tolist())]


def transcribe(audio) -> tuple[str, str]:
    import torch
    proc, model = _state["wproc"], _state["whisper"]
    feats = proc(audio, sampling_rate=RATE, return_tensors="pt").input_features
    prompt = proc.get_prompt_ids(NAMES_PROMPT, return_tensors="pt") if NAMES_PROMPT else None
    with torch.no_grad():
        ids = model.generate(feats, max_new_tokens=96, task="transcribe",
                             **({"prompt_ids": prompt} if prompt is not None else {}))
    text = proc.batch_decode(ids, skip_special_tokens=True)[0].strip()
    if NAMES_PROMPT and text.startswith(NAMES_PROMPT.strip()):
        text = text[len(NAMES_PROMPT.strip()):].strip()   # older generate() echoes the prompt
    raw = proc.batch_decode(ids, skip_special_tokens=False)[0]
    m = re.search(r"<\|([a-z]{2,3})\|>", raw)
    return re.sub(r"\s+", " ", text), (m.group(1) if m else "")


def hear(body: bytes, rate: int) -> dict:
    audio, rms, seconds = pcm_to_audio(body, rate)
    result = {"sounds": [], "speech": "", "language": "", "speech_score": 0.0,
              "rms": round(rms, 1), "seconds": round(seconds, 2), "ms": {}, "errors": {}}
    all_sounds = []
    if _state["ast"] is not None:
        t = time.monotonic()
        try:
            all_sounds = classify(audio)
        except Exception as exc:  # noqa: BLE001
            result["errors"]["ast"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        result["ms"]["ast"] = int((time.monotonic() - t) * 1000)
    speech_score = max([s["score"] for s in all_sounds if s["label"].lower() in SPEECHY] or [0.0])
    result["speech_score"] = round(speech_score, 3)
    result["sounds"] = [s for s in all_sounds if s["score"] >= MIN_SOUND_SCORE][:TOP_SOUNDS]
    run_whisper = _state["whisper"] is not None and (speech_score >= SPEECH_GATE or _state["ast"] is None)
    if run_whisper:
        t = time.monotonic()
        try:
            text, lang = transcribe(audio)
            if text.lower() in HALLUCINATIONS and speech_score < 0.5:
                text = ""
            result["speech"], result["language"] = text[:300], lang
        except Exception as exc:  # noqa: BLE001
            result["errors"]["whisper"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        result["ms"]["whisper"] = int((time.monotonic() - t) * 1000)
    del audio
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
            models = {"ast": _state["ast"] is not None, "whisper": _state["whisper"] is not None}
            status = "loading" if _state["loading"] else ("ok" if all(models.values()) else "degraded")
            self._json(200, {"status": status, "models": models, "errors": _state["errors"]})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        from urllib.parse import parse_qs, urlparse
        url = urlparse(self.path)
        if url.path != "/hear":
            self._json(404, {"error": "not found"})
            return
        try:
            rate = int(parse_qs(url.query).get("rate", ["48000"])[0])
        except ValueError:
            self._json(400, {"error": "rate must be an integer"})
            return
        n = int(self.headers.get("Content-Length", 0))
        if n <= 0 or n > int(MAX_S * 48000 * 2) + 4096:
            self._json(400, {"error": "invalid content length"})
            return
        body = self.rfile.read(n)
        if _state["loading"]:
            self._json(503, {"error": "models still loading"})
            return
        try:
            with _lock:
                out = hear(body, rate)
            self._json(200, out)
        except ValueError as exc:
            self._json(400, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            self._json(422, {"error": f"{type(exc).__name__}: {str(exc)[:160]}"})
        finally:
            del body

    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5052)
    ap.add_argument("--bind", default="0.0.0.0")   # Lynx posts clips over the LAN
    args = ap.parse_args()
    threading.Thread(target=load_models, daemon=True).start()
    ThreadingHTTPServer((args.bind, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
