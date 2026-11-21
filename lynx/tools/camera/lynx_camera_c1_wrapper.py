#!/usr/bin/env python3
"""Lynx Camera C1 Wrapper for the first live camera test (SPEC C1, #292, #308).

After Aria runs attended Stage A (patched ISP insmod) and Stage B (one frame capture)
with Noob present, this wrapper:
1. Loads the captured frame in memory (from trial dir, specific file, or stdin).
   If raw Bayer data is provided, lifts RGGB -> PNG in memory via decode_camera_bayer.
   Fails loudly if the image cannot be decoded.
2. Checks staleness: trial frame must match current Lynx boot and be < 5 minutes old.
3. Sends image bytes in memory to the Nexus detection service (:5050/detect).
4. Normalizes multi-word labels (e.g. 'cell phone' -> 'cell_phone') for canonical sense lines:
   'NOOBIA P1 camera object.seen label=<norm_label> conf=<conf> | <label> seen by camera'
5. Emits ON LYNX over SSH into Lynx's syslog (/var/log/lynx/messages) via busybox logger.
6. Frames remain strictly in memory; zero persistent disk writes.
"""

from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time
import urllib.request
import urllib.error

# Resolve repository paths
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
AUTONOMY_DIR = REPO / "common" / "autonomy"
LYNX_TOOLS_DIR = REPO / "lynx" / "tools"

for p in (AUTONOMY_DIR, LYNX_TOOLS_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

try:
    from sense import format_line
except ImportError:
    format_line = None

try:
    from PIL import Image, ImageChops
    from decode_camera_bayer import planes
    from preview_lut import make_lut
    HAS_BAYER_DECODER = True
except ImportError:
    HAS_BAYER_DECODER = False

DEFAULT_DETECT_URL = "http://127.0.0.1:5050/detect"
DEFAULT_TIMEOUT_S = 8.0
MAX_FRAME_SIZE = 10 * 1024 * 1024  # 10 MB limit
DEFAULT_LYNX_IP = "192.168.100.107"
DEFAULT_LYNX_PORT = 2222
STALENESS_MAX_AGE_S = 300.0  # 5 minutes


def normalize_coco_label(label: str) -> str:
    """Normalize multi-word COCO labels into valid sense field values [a-z0-9_]."""
    norm = re.sub(r"[^a-z0-9_]+", "_", label.strip().lower()).strip("_")
    return norm or "unknown"


def lift_bayer_to_png(raw_bytes: bytes, width: int = 1600, height: int = 1200) -> bytes:
    """Lift raw RGGB Bayer frame bytes to PNG bytes in memory."""
    if not HAS_BAYER_DECODER:
        raise RuntimeError("Bayer decoder dependencies (PIL, decode_camera_bayer) unavailable")
    expected = width * height
    if len(raw_bytes) != expected:
        raise ValueError(f"expected {expected} Bayer bytes for {width}x{height}, got {len(raw_bytes)}")

    red, green_top, green_bottom, blue = planes(raw_bytes, phase="rggb", width=width, height=height)
    green = ImageChops.add(green_top, green_bottom, scale=2)
    rgb = Image.merge(
        "RGB",
        tuple(channel.resize((width, height), Image.Resampling.BILINEAR) for channel in (red, green, blue)),
    )
    lut = make_lut(16, 3.0, 1.8)
    lifted = rgb.point(lut * 3)

    buf = io.BytesIO()
    lifted.save(buf, format="PNG")
    return buf.getvalue()


def ensure_decodable_image(raw_bytes: bytes, source_hint: str = "") -> bytes:
    """Verify bytes are a valid image format (PNG/JPEG) or decode raw Bayer.

    Fails loudly if undecodable; never passes invalid bytes to detector.
    """
    if not raw_bytes:
        raise ValueError(f"empty image payload from {source_hint or 'source'}")

    # Check if directly decodable as image (PNG, JPEG, etc.)
    try:
        from PIL import Image
        with Image.open(io.BytesIO(raw_bytes)) as img:
            img.verify()
        return raw_bytes
    except Exception:
        pass

    # Check if raw Bayer payload (1600x1200 sensor4 mode)
    if len(raw_bytes) == 1600 * 1200 or source_hint.endswith((".bayer", "download_frame.stdout")):
        try:
            return lift_bayer_to_png(raw_bytes, width=1600, height=1200)
        except Exception as exc:
            raise ValueError(f"failed to decode raw Bayer frame from {source_hint}: {exc}") from exc

    raise ValueError(
        f"frame from {source_hint or 'source'} ({len(raw_bytes)} bytes) is undecodable (not valid PNG/JPEG/Bayer)"
    )


def get_current_lynx_boot_id(
    ip: str = DEFAULT_LYNX_IP,
    port: int = DEFAULT_LYNX_PORT,
    timeout_s: float = 5.0,
    ssh_fn=None,
) -> str:
    """Retrieve current boot ID from Lynx over pinned SSH."""
    if ssh_fn:
        rc, out, _ = ssh_fn("cat /proc/sys/kernel/random/boot_id")
        if rc == 0 and out.strip():
            return out.strip().splitlines()[-1].strip()
        raise RuntimeError(f"failed to read boot ID via custom ssh (exit={rc})")

    try:
        from lynx_wifi_v19_contact import ssh_command
        argv = ssh_command(ip, "cat /proc/sys/kernel/random/boot_id")
        argv[-2:-2] = ["-p", str(port)]
        res = subprocess.run(argv, capture_output=True, text=True, timeout=timeout_s)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip().splitlines()[-1].strip()
        raise RuntimeError(f"ssh returned exit {res.returncode}: {res.stderr.strip()}")
    except Exception as exc:
        raise RuntimeError(f"unable to reach Lynx on {ip}:{port} to read current boot_id: {exc}") from exc


def find_latest_trial_frame(
    logs_root: Path | str = REPO / "lynx" / "logs",
    expected_boot_id: str | None = None,
    max_age_s: float = STALENESS_MAX_AGE_S,
    now_ts: float | None = None,
) -> Path:
    """Find the newest Stage B trial directory matching boot ID and staleness window."""
    root = Path(logs_root)
    if not root.is_dir():
        raise FileNotFoundError(f"logs root not found: {root}")

    # Glob both camera-camsv-frame-* and legacy camsv-frame-*
    dirs = sorted(
        list(root.glob("camera-camsv-frame-*")) + list(root.glob("camsv-frame-*")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not dirs:
        raise FileNotFoundError(f"no Stage B camera trial directories found under {root}")

    now = now_ts if now_ts is not None else time.time()

    for d in dirs:
        # Check staleness via result.json if present
        res_file = d / "result.json"
        boot_id_file = d / "boot_id.stdout"
        dir_boot_id = None
        capture_time = d.stat().st_mtime

        if res_file.is_file():
            try:
                res_data = json.loads(res_file.read_text())
                steps = res_data.get("steps", [])
                for s in steps:
                    if s.get("name") == "boot_id" and "unix_ns" in s:
                        capture_time = s["unix_ns"] / 1e9
                        break
            except Exception:
                pass

        if boot_id_file.is_file():
            dir_boot_id = boot_id_file.read_text().strip()

        # Enforce boot_id match if required
        # An unknown boot is refused, not trusted: a frame we cannot tie to
        # this boot could be from yesterday (Gwyn review of 87f7e6f).
        if expected_boot_id and dir_boot_id != expected_boot_id:
            continue

        # Enforce staleness window (<= 5 minutes)
        if abs(now - capture_time) > max_age_s:
            continue

        # Look for valid frame file within candidate dir
        for cand in ("sensor4-preview-lifted.png", "sensor4-lifted.png", "sensor4.bayer", "download_frame.stdout"):
            f = d / cand
            if f.is_file() and f.stat().st_size > 0:
                return f

    raise RuntimeError(
        f"no fresh trial frame found in {root} matching boot_id={expected_boot_id} within {max_age_s}s"
    )


def read_frame_bytes(
    path: Path | str | None = None,
    use_latest: bool = False,
    stdin: bool = False,
    logs_root: Path | str = REPO / "lynx" / "logs",
    expected_boot_id: str | None = None,
    max_age_s: float = STALENESS_MAX_AGE_S,
    now_ts: float | None = None,
) -> tuple[bytes, str]:
    """Read frame bytes into memory and ensure valid image decoding without disk persistence."""
    if stdin:
        data = sys.stdin.buffer.read(MAX_FRAME_SIZE + 1)
        if len(data) > MAX_FRAME_SIZE:
            raise ValueError(f"frame from stdin exceeds {MAX_FRAME_SIZE} bytes")
        img_bytes = ensure_decodable_image(data, source_hint="stdin")
        return img_bytes, "stdin"

    target_path: Path | None = None
    if path:
        target_path = Path(path)
    elif use_latest:
        target_path = find_latest_trial_frame(
            logs_root=logs_root,
            expected_boot_id=expected_boot_id,
            max_age_s=max_age_s,
            now_ts=now_ts,
        )
    else:
        raise ValueError("must specify --frame-path, --latest-trial, or --stdin")

    if not target_path.is_file():
        raise FileNotFoundError(f"frame file not found: {target_path}")

    size = target_path.stat().st_size
    if size > MAX_FRAME_SIZE:
        raise ValueError(f"frame file {target_path} exceeds {MAX_FRAME_SIZE} bytes")

    raw_bytes = target_path.read_bytes()
    img_bytes = ensure_decodable_image(raw_bytes, source_hint=str(target_path))
    return img_bytes, str(target_path)


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


def emit_line_to_lynx(
    line: str,
    ip: str = DEFAULT_LYNX_IP,
    port: int = DEFAULT_LYNX_PORT,
    timeout_s: float = 10.0,
) -> None:
    """Emit formatted sense line directly onto Lynx's syslog over pinned SSH."""
    from lynx_wifi_v19_contact import ssh_command

    remote_cmd = f"busybox logger -t noobia-sense -p user.notice {shlex.quote(line)}"
    argv = ssh_command(ip, remote_cmd)
    argv[-2:-2] = ["-p", str(port)]
    res = subprocess.run(argv, capture_output=True, text=True, timeout=timeout_s)
    if res.returncode != 0:
        raise RuntimeError(f"failed to emit sense line to Lynx (exit={res.returncode}): {res.stderr.strip()}")


def run_c1_wrapper(
    frame_bytes: bytes,
    frame_source: str,
    detect_url: str = DEFAULT_DETECT_URL,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    do_emit: bool = False,
    detect_fn=None,
    emit_remote_fn=None,
) -> dict:
    """Execute C1 detection and emit canonical sense lines onto Lynx."""
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
            if emit_remote_fn:
                emit_remote_fn(line)
            else:
                emit_line_to_lynx(line)
    else:
        for obj in objects:
            label = str(obj.get("label", "unknown")).strip()
            norm_label = normalize_coco_label(label)
            conf = float(obj.get("confidence", 0.0))
            conf_str = f"{conf:.2f}"
            text = f"{label} seen by camera"
            if format_line:
                line = format_line(1, "camera", "object.seen", fields={"label": norm_label, "conf": conf_str}, text=text)
            else:
                line = f"NOOBIA P1 camera object.seen label={norm_label} conf={conf_str} | {text}"
            lines.append(line)

            if do_emit:
                if emit_remote_fn:
                    emit_remote_fn(line)
                else:
                    emit_line_to_lynx(line)

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
    parser.add_argument("--boot-id", default=None, help="Expected Lynx boot ID (defaults to reading live from Lynx)")
    parser.add_argument("--detect-url", default=DEFAULT_DETECT_URL, help=f"Nexus detect service URL (default: {DEFAULT_DETECT_URL})")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S, help="Detection timeout in seconds")
    parser.add_argument("--emit", action="store_true", help="Emit formatted sense line to Lynx syslog (noobia-sense)")
    parser.add_argument("--logs-root", type=Path, default=REPO / "lynx" / "logs", help="Root logs directory for Stage B trials")

    args = parser.parse_args(argv)

    try:
        expected_boot = args.boot_id
        if args.latest_trial and not expected_boot:
            try:
                expected_boot = get_current_lynx_boot_id()
            except Exception as err:
                print(f"Warning: could not query live boot_id from Lynx: {err}", file=sys.stderr)

        frame_bytes, source_desc = read_frame_bytes(
            path=args.frame_path,
            use_latest=args.latest_trial,
            stdin=args.stdin,
            logs_root=args.logs_root,
            expected_boot_id=expected_boot,
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
