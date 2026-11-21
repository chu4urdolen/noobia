#!/usr/bin/env python3
"""S1 camera sense for Lynx (PLAN S1): single-frame capture and object detection.

Sampled / event sense:
- Captures one bounded JPEG frame in memory via V4L2/CAMSV-0 (lynx-camera-capture).
- Sends frame in memory to Nexus object detection service (port 5050).
- Emits NOOBIA P1 camera object.seen on NEW labels (unseen or not seen in >= 300s).
- Emits NOOBIA P0 camera object.seen on repeated labels.
- Strictly zero frame persistence on disk.
- Enforces hardware disable switch (/etc/lynx/disable-camera-capture or /etc/noobia/camera.disable).

Convention:
Honest failure when camera device or Nexus detect service is unavailable.
Does not take down the senses loop.

    python3 /usr/local/lib/noobia/senses/camera/lynx_sense_camera.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
import urllib.request
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from lynx_senses_lib import (  # noqa: E402
    SenseUnavailable,
    base_result,
    clean_field,
    clean_text,
    emit_line,
    failure,
    finish,
    import_sense,
    load_state,
    now_ts,
    save_state,
    state_path,
)

DEFAULT_DETECT_URL = "http://192.168.100.106:5050/detect"
DEFAULT_DEVICE = "/dev/video145"
DEFAULT_DISABLE_SWITCH = "/etc/lynx/disable-camera-capture"
NOOBIA_CAMERA_DISABLE = "/etc/noobia/camera.disable"
SEEN_WINDOW_S = 300.0
CAPTURE_TIMEOUT_S = 3.0
DETECT_TIMEOUT_S = 5.0
DEFAULT_CAPTURE_TOOL = "/usr/local/bin/lynx-camera-capture"
CAPTURE_TOOL_TIMEOUT_S = 8.0
MAX_FRAME_BYTES = 4 * 1024 * 1024


def is_camera_disabled(switch: str | Path = DEFAULT_DISABLE_SWITCH) -> bool:
    return Path(switch).exists() or Path(NOOBIA_CAMERA_DISABLE).exists()


def default_capture(device: str = DEFAULT_DEVICE, timeout_s: float = CAPTURE_TIMEOUT_S) -> tuple[bool, bytes, str]:
    """Capture one frame via the installed H2 tool (lynx-camera-capture --stdout),
    zero frame persistence; falls back to the repo module for dev on Nexus.

    The H2 packet installs the tool as a standalone executable
    (/usr/local/bin/lynx-camera-capture) - there is no importable lynx
    package on Lynx - so the subprocess is the primary path there.
    """
    import subprocess

    tool = os.environ.get("NOOBIA_CAMERA_CAPTURE", DEFAULT_CAPTURE_TOOL)
    if Path(tool).is_file():
        try:
            proc = subprocess.run(
                [tool, "--stdout", "--device", device, "--timeout", str(timeout_s)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=CAPTURE_TOOL_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            return False, b"", f"capture tool timed out after {CAPTURE_TOOL_TIMEOUT_S}s"
        except OSError as exc:
            return False, b"", f"capture tool failed to start: {exc}"
        if proc.returncode != 0:
            detail = proc.stderr.decode("utf-8", "replace").strip()[:160]
            return False, b"", detail or f"capture tool exited {proc.returncode}"
        frame = proc.stdout[:MAX_FRAME_BYTES + 1]
        if len(frame) > MAX_FRAME_BYTES:
            return False, b"", "capture tool output exceeds the 4 MiB bound"
        if not frame:
            return False, b"", "capture tool produced no frame"
        return True, frame, f"captured {len(frame)} bytes via {Path(tool).name}"

    # Repo/dev fallback (Nexus checkout where the package is importable).
    try:
        from lynx.tools.camera.lynx_camera_capture import capture_one_frame
        return capture_one_frame(device=device, timeout_s=timeout_s)
    except ImportError:
        pass

    if not Path(device).exists():
        return False, b"", f"device {device} not present and capture tool not installed"
    return False, b"", "capture tool not installed (H2) and module not importable"


def default_detect(frame_bytes: bytes, detect_url: str = DEFAULT_DETECT_URL, timeout_s: float = DETECT_TIMEOUT_S) -> list[dict]:
    """Post frame to Nexus detection service (:5050/detect)."""
    req = urllib.request.Request(
        detect_url,
        data=frame_bytes,
        headers={"Content-Type": "image/jpeg"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("objects", [])


def run(
    dry_run: bool = False,
    state_file: str | None = None,
    capture_fn=None,
    detect_fn=None,
    detect_url: str | None = None,
    now: float | None = None,
) -> tuple[dict, int]:
    """One camera sample. capture_fn and detect_fn are injectable for testing."""
    t = float(now if now is not None else now_ts())
    try:
        sense = import_sense()
    except SenseUnavailable as exc:
        return failure("camera", exc)

    if is_camera_disabled():
        return (base_result("camera", disabled=True, emitted=[], info="camera inhibited by disable switch"), 0)

    # 1. Capture frame
    cap = capture_fn or default_capture
    ok, frame_bytes, cap_msg = cap()
    if not ok:
        return (base_result("camera", available=False, emitted=[], detail=cap_msg), 0)

    # 2. Detect objects
    det_url = detect_url or os.environ.get("NOOBIA_DETECT_URL", DEFAULT_DETECT_URL)
    det = detect_fn or (lambda b: default_detect(b, detect_url=det_url))
    try:
        objects = det(frame_bytes)
    except Exception as exc:
        return failure("camera", exc)

    path = state_path("camera", state_file)
    state = load_state(path)
    last_seen: dict[str, float] = state.get("last_seen", {})
    emitted: list[str] = []

    for obj in objects:
        label = clean_field(obj.get("label", "unknown"))
        conf = float(obj.get("confidence", 0.0))
        prev_time = last_seen.get(label)

        # P1 on new label (never seen or elapsed >= SEEN_WINDOW_S)
        is_new = (prev_time is None) or (t - prev_time >= SEEN_WINDOW_S)
        p = 1 if is_new else 0

        last_seen[label] = t
        conf_str = f"{conf:.2f}"
        text_desc = f"{label} seen by camera"
        line = emit_line(
            sense,
            p,
            "camera",
            "object.seen",
            fields={"label": label, "conf": conf_str},
            text=text_desc,
            dry_run=dry_run,
        )
        emitted.append(line)

    state["last_seen"] = last_seen
    state["last_objects_count"] = len(objects)
    state["t"] = t

    if not dry_run:
        save_state(path, state)

    return (
        base_result(
            "camera",
            sampled={"objects_count": len(objects), "labels": [o.get("label") for o in objects]},
            emitted=emitted,
            state=state,
        ),
        0,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dry-run", action="store_true", help="print would-be sense lines; never write state or syslog")
    parser.add_argument("--state-file", default=None, help="state file override")
    args = parser.parse_args(argv)
    try:
        result, code = run(dry_run=args.dry_run, state_file=args.state_file)
    except (OSError, LookupError, ValueError) as exc:
        result, code = failure("camera", exc)
    return finish(result, code)


if __name__ == "__main__":
    sys.exit(main())
