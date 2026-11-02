#!/usr/bin/env python3
"""Record bounded, read-only LIGHT_RAW samples for a physical response test."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parent.parent
CLIENT = ROOT / "tools/lynx_noobctl.py"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration-seconds", type=int, default=30)
    args = parser.parse_args()
    if not 5 <= args.duration_seconds <= 60:
        parser.error("duration must be 5..60 seconds")
    os.umask(0o077)
    out = ROOT / "logs" / f"rear-light-response-{time.time_ns()}"
    out.mkdir(mode=0o700)
    rows = []
    deadline = time.monotonic() + args.duration_seconds
    while time.monotonic() < deadline:
        started = time.time_ns()
        try:
            result = subprocess.run(["python3", str(CLIENT), "CALL", "LIGHT_RAW"],
                                    capture_output=True, text=True, timeout=5)
            row = {"unix_ns": started, "exit": result.returncode,
                   "reply": result.stdout.strip(), "error": result.stderr.strip()[:300]}
        except subprocess.TimeoutExpired:
            row = {"unix_ns": started, "error": "timeout"}
        rows.append(row)
        print(json.dumps(row), flush=True)
        pause = min(1.0, deadline - time.monotonic())
        if pause > 0:
            time.sleep(pause)
    (out / "result.json").write_text(json.dumps({"schema": 1, "samples": rows}, indent=2) + "\n")
    print(json.dumps({"receipt": str(out / "result.json"), "samples": len(rows)}))


if __name__ == "__main__":
    main()
