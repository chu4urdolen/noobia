#!/usr/bin/env python3
"""Lynx Camera C1 Wrapper for the first live camera test (SPEC C1, #292).

After Aria runs attended Stage A (patched ISP insmod) and Stage B (one frame capture)
with Noob present, this wrapper:
1. Loads the captured frame in memory (from trial dir, specific file, or stdin).
2. Sends the image bytes in memory to the Nexus detection service (:5050/detect).
3. Formats and emits canonical NOOBIA sense lines via common/autonomy/sense.py:
   'NOOBIA P1 camera object.seen label=<label> conf=<conf> | <label> seen by camera'
4. Frames remain strictly in memory; zero persistent disk writes.
5. All operations are strictly bounded by timeouts.
"""

from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import sys
import time
import urllib.request
import urllib.error

# Resolve repository paths
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
AUTONOMY_DIR = REPO / "common" / "autonomy"
if str(AUTONOMY_DIR) not in sys.path:
    sys.path.insert(0, str(AUTONOMY_DIR))

try:
    from sense import format_line, emit
except ImportError:
    # Fallback to local import helper if installed on target
    format_line = None
    emit = None

DEFAULT_DETECT_URL = "http://127.0.0.1:5050/detect"
DEFAULT_TIMEOUT_S = 8.0
MAX_FRAME_SIZE = 10 * 1024 * 1024  # 10 MB limit


def find_latest_trial_frame(logs_root: Path | str = REPO / "lynx" / "logs") -> Path | None:
    """Find the newest Stage B trial directory containing a valid frame."""
    root = Path(logs_root)
    if not root.is_dir():
        return None

    # Find camsv-frame-* dirs sorted by modification time descending
    dirs = sorted(root.glob("camsv-frame-*"), key=lambda p: p.stat().st_mtime, reverse=True)
    for d in dirs:
        # Check for decoded image first (PNG or JPEG), then raw bayer frame
        for cand in ("sensor4-lifted.png", "lifted.png", "download_frame.stdout", "sensor4.bayer"):
            f = d / cand
            if f.is_file() and f.stat().st_size > 0:
                return f
    return None


def read_frame_bytes(
    path: Path | str | None = None,
    use_latest: bool = False,
    stdin: bool = False,
    logs_root: Path | str = REPO / "lynx" / "logs",
) -> tuple[bytes, str]:
    """Read frame bytes into memory strictly without writing to disk."""
    if stdin:
        data = sys.stdin.buffer.read(MAX_FRAME_SIZE + 1)
        if len(data) > MAX_FRAME_SIZE:
            raise ValueError(f"frame from stdin exceeds {MAX_FRAME_SIZE} bytes")
        return data, "stdin"

    target_path: Path | None = None
    if path:
        target_path = Path(path)
    elif use_latest:
        target_path = find_latest_trial_frame(logs_root)
        if not target_path:
            raise FileNotFoundError(f"no Stage B trial frames found in {logs_root}")
    else:
        raise ValueError("must specify --frame-path, --latest-trial, or --stdin")

    if not target_path.is_file():
        raise FileNotFoundError(f"frame file not found: {target_path}")

    size = target_path.stat().st_size
    if size > MAX_FRAME_SIZE:
        raise ValueError(f"frame file {target_path} exceeds {MAX_FRAME_SIZE} bytes")

    return target_path.read_bytes(), str(target_path)


def detect_objects(
    frame_bytes: bytes,
    detect_url: str = DEFAULT_DETECT_URL,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> list[dict]:
    """Query Nexus detection service (:5050/detect) with in-memory frame bytes."""
    req = urllib.request.Request(
        detect_url,
        data=frame_bytes,
        headers={"Content-Type": "application/octet-stream"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("objects", [])
    except urllib.error.URLError as err:
        raise ConnectionError(f"Nexus detect service unavailable at {detect_url}: {err}") from err


def run_c1_wrapper(
    frame_bytes: bytes,
    frame_source: str,
    detect_url: str = DEFAULT_DETECT_URL,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    do_emit: bool = False,
    detect_fn=None,
    emit_fn=None,
) -> dict:
    """Execute C1 detection and sense line emission."""
    det = detect_fn or (lambda b: detect_objects(b, detect_url=detect_url, timeout_s=timeout_s))
    objects = det(frame_bytes)

    lines: list[str] = []
    # If no objects detected, produce one P0 informational observation
    if not objects:
        text = "frame analyzed, no objects recognized"
        if format_line:
            line = format_line(0, "camera", "frame.analyzed", fields={"objects": "0"}, text=text)
        else:
            line = f"NOOBIA P0 camera frame.analyzed objects=0 | {text}"
        lines.append(line)
        if do_emit:
            if emit_fn:
                emit_fn(0, "camera", "frame.analyzed", fields={"objects": "0"}, text=text)
            elif emit:
                emit(0, "camera", "frame.analyzed", fields={"objects": "0"}, text=text)
    else:
        for obj in objects:
            label = str(obj.get("label", "unknown")).strip()
            conf = float(obj.get("confidence", 0.0))
            conf_str = f"{conf:.2f}"
            text = f"{label} seen by camera"
            if format_line:
                line = format_line(1, "camera", "object.seen", fields={"label": label, "conf": conf_str}, text=text)
            else:
                line = f"NOOBIA P1 camera object.seen label={label} conf={conf_str} | {text}"
            lines.append(line)

            if do_emit:
                if emit_fn:
                    emit_fn(1, "camera", "object.seen", fields={"label": label, "conf": conf_str}, text=text)
                elif emit:
                    emit(1, "camera", "object.seen", fields={"label": label, "conf": conf_str}, text=text)

    return {
        "ok": True,
        "frame_source": frame_source,
        "frame_bytes": len(frame_bytes),
        "objects_count": len(objects),
        "objects": objects,
        "emitted_lines": lines,
        "emitted": bool(do_emit),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--frame-path", type=Path, default=None, help="Path to captured frame file (PNG/JPEG/Bayer)")
    parser.add_argument("--latest-trial", action="store_true", help="Automatically load newest Stage B trial frame")
    parser.add_argument("--stdin", action="store_true", help="Read frame bytes from standard input")
    parser.add_argument("--detect-url", default=DEFAULT_DETECT_URL, help=f"Nexus detect service URL (default: {DEFAULT_DETECT_URL})")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S, help="Detection timeout in seconds")
    parser.add_argument("--emit", action="store_true", help="Emit formatted sense line to syslog (noobia-sense)")
    parser.add_argument("--logs-root", type=Path, default=REPO / "lynx" / "logs", help="Root logs directory for Stage B trials")

    args = parser.parse_args(argv)

    try:
        frame_bytes, source_desc = read_frame_bytes(
            path=args.frame_path,
            use_latest=args.latest_trial,
            stdin=args.stdin,
            logs_root=args.logs_root,
        )
        res = run_c1_wrapper(
            frame_bytes=frame_bytes,
            frame_source=source_desc,
            detect_url=args.detect_url,
            timeout_s=args.timeout,
            do_emit=args.emit,
        )
        print(json.dumps(res, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
