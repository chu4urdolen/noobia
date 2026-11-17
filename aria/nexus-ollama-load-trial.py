#!/usr/bin/env python3
"""Bounded local Ollama inference load with fsynced GPU and request receipts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import threading
import time
import urllib.request


MODEL = "gpt-oss:20b"
URL = "http://127.0.0.1:11434/api/generate"
PROMPT = ("Write a long numbered field guide to designing a reliable, repairable "
          "small Linux device. Each entry should contain a different concrete "
          "diagnostic step, its expected observation, and a failure interpretation. "
          "Continue through at least 200 entries before concluding.")


def cpu_worker(stop: multiprocessing.Event) -> None:
    block = b"Nexus bounded power trial " * (8 * 1024 * 1024 // 26)
    while not stop.is_set():
        hashlib.sha256(block).digest()


def append(path: Path, record: dict) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, separators=(",", ":")) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def gpu_samples(path: Path, stop: threading.Event) -> None:
    while not stop.is_set():
        started = time.monotonic()
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=power.draw,temperature.gpu,utilization.gpu,power.limit",
             "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5)
        append(path, {"time": time.time(), "gpu_csv": result.stdout.strip(),
                      "exit": result.returncode})
        stop.wait(max(0, 1.0 - (time.monotonic() - started)))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=int, default=180)
    parser.add_argument("--cpu-workers", type=int, default=0)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if not 30 <= args.seconds <= 600 or not 0 <= args.cpu_workers <= 8:
        parser.error("seconds must be 30..600 and cpu-workers 0..8")
    out = args.out.resolve()
    if not out.is_relative_to(Path("/noobia/aria/logs")):
        parser.error("output must be under /noobia/aria/logs")
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.chmod(out, 0o700)
    events = out / "requests.jsonl"
    samples = out / "gpu-1s.jsonl"
    stop = threading.Event()
    cpu_stop = multiprocessing.Event()
    workers = [multiprocessing.Process(target=cpu_worker, args=(cpu_stop,), daemon=True)
               for _ in range(args.cpu_workers)]
    for worker in workers:
        worker.start()
    sampler = threading.Thread(target=gpu_samples, args=(samples, stop), daemon=True)
    sampler.start()
    deadline = time.monotonic() + args.seconds
    request_count = 0
    try:
        append(events, {"type": "trial_start", "cpu_workers": args.cpu_workers,
                        "seconds": args.seconds, "time": time.time()})
        while time.monotonic() < deadline:
            request_count += 1
            started = time.monotonic()
            append(events, {"type": "request_start", "number": request_count,
                            "time": time.time()})
            body = json.dumps({"model": MODEL, "prompt": PROMPT, "stream": True,
                               "options": {"num_predict": 2048, "temperature": 0.6},
                               "keep_alive": "5m"}).encode()
            request = urllib.request.Request(URL, data=body,
                                             headers={"Content-Type": "application/json"})
            tokens = 0
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    for line in response:
                        item = json.loads(line)
                        if item.get("done"):
                            tokens = item.get("eval_count", 0)
                            break
                append(events, {"type": "request_done", "number": request_count,
                                "elapsed_s": round(time.monotonic()-started, 2),
                                "eval_count": tokens, "time": time.time()})
                print(f"request {request_count}: {tokens} tokens in "
                      f"{time.monotonic()-started:.1f}s", flush=True)
            except Exception as exc:
                append(events, {"type": "request_error", "number": request_count,
                                "error": str(exc), "time": time.time()})
                raise
        append(events, {"type": "trial_done", "requests": request_count,
                        "time": time.time(), "utc": datetime.now(timezone.utc).isoformat()})
        return 0
    finally:
        stop.set()
        sampler.join(timeout=6)
        cpu_stop.set()
        for worker in workers:
            worker.join(timeout=5)
            if worker.is_alive():
                worker.terminate()
                worker.join(timeout=2)
        print(f"receipt: {out}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
