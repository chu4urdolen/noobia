#!/usr/bin/env python3
"""One real camera look for Lynx: lock -> CAMSV capture -> Nexus detection.

Shared by the camera sense (once a minute) and Lynx's own photo tool, so the
two can never use the camera at the same time (ARCHITECTURE 5a.5):

- One lock, /run/lynx/camera.lock (flock). The sense never waits for it: if
  Lynx is taking her own picture, the sense skips that minute. Her tool
  waits a few seconds for a sense capture to finish.
- Capture is the proven streaming helper (lynx_camsv_dmabuf_capture.py,
  installed as /usr/local/libexec/lynx/lynx-camsv-capture): one bounded
  frame, no camera-control ioctls (G_EXT_CTRLS crashes this kernel), raw
  RGGB Bayer written to RAM (/run), read, and deleted at once.
- Lynx has no numpy/PIL, so the raw frame goes to Nexus
  POST /detect_bayer, which decodes, rotates upright, white-balances and
  detects (common/autonomy/services/detect/service.py).
- Honest failure: every problem is returned as an error string; nothing is
  ever reported as "seen" or "empty" unless a real frame was analysed.

Camera stack: the CAMSV route must be prepared for this boot first
(prepare_camera_camsv.py --execute --attended). Without it /dev/video145 is
absent and look() says so.
"""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.error
import urllib.request

LOCK = Path(os.environ.get("LYNX_CAMERA_LOCK", "/run/lynx/camera.lock"))
CAPTURE = os.environ.get("LYNX_CAMSV_CAPTURE", "/usr/local/libexec/lynx/lynx-camsv-capture")
FRAME = Path(os.environ.get("LYNX_CAMERA_FRAME", "/run/lynx/camera-look.bayer"))
DEVICE = Path(os.environ.get("LYNX_CAMERA_DEVICE", "/dev/video145"))
DETECT_URL = os.environ.get("NOOBIA_DETECT_BAYER_URL", "http://192.168.100.106:5050/detect_bayer")
DISABLE = (Path("/etc/lynx/disable-camera-capture"), Path("/etc/noobia/camera.disable"))
WIDTH, HEIGHT = 1600, 1200          # sensor4 (GC02M1, rear) CAMSV baseline
# The stock camera firmware the CCU/SCP drivers request at stream-on, as the
# proven trial stages it (trial_camera_camsv_frame.py FIRMWARE_FILES). Kept
# on storage; the kernel firmware path points here ONLY during a capture and
# is always restored to /vendor/firmware.
FW_DIR = Path(os.environ.get("LYNX_CAMERA_FW", "/usr/local/lib/lynx/camera-fw"))
FW_FILES = {"lib3a.ccu_dummy": "6f8d51193a28c9279d403bda99e008f12af4f20add5d1154ee7f3523381ffdde",
            "remoteproc_scp": "66687aadf862bd776c8fc18b8e9f8e20089714856ee233b3902a591d0d5f2925"}
FW_PATH = Path(os.environ.get("LYNX_FIRMWARE_PATH_PARAM", "/sys/module/firmware_class/parameters/path"))
FW_DEFAULT = "/vendor/firmware"
V4L2_CTL = os.environ.get("LYNX_V4L2_CTL", "/usr/bin/v4l2-ctl")
SETTLE_MS = 750
CAPTURE_TIMEOUT_S = 20.0            # helper waits at most 9 s for the frame
DETECT_TIMEOUT_S = 50.0           # strong models (YOLO11x + Florence-2) take ~22 s on CPU
CAMERA = "back"

# Both rear cameras Aria proved on 2026-11-21 (forge note on lynx): the macro
# GC02M1 (sensor4) and the wide IMX355 (sensor2). They share CAMSV-0; the
# route (two media links each, pinned IDs from camera_route_plan.py) decides
# which sensor feeds it. The macro route is the resting state: a wide look
# switches to sensor2 and ALWAYS switches back, verified, afterwards.
CAMERAS = {
    "back": {"sensor": 4, "w": 1600, "h": 1200, "links": ((45, 0, 27, 0), (27, 1, 615, 0)), "seninf": 27},
    "wide": {"sensor": 2, "w": 3264, "h": 2448, "links": ((71, 0, 53, 0), (53, 1, 615, 0)), "seninf": 53},
}
MEDIA = os.environ.get("LYNX_CAMERA_MEDIA", "/dev/media1")
MEDIA_CTL = os.environ.get("LYNX_MEDIA_CTL", "/usr/bin/media-ctl")


def _link(link, enabled: bool) -> str:
    src, sp, sink, kp = link
    return f"{src}:{sp}->{sink}:{kp}[{5 if enabled else 4}]"   # DYNAMIC bit required


def current_route(run=subprocess.run) -> str | None:
    """'back', 'wide' or None (unknown/partial) from the live media graph."""
    try:
        g = run([MEDIA_CTL, "-d", MEDIA, "-p"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    def active(name):
        cam = CAMERAS[name]
        block = g.split(f"entity {cam['seninf']}: seninf-", 1)
        if len(block) < 2:
            return False
        block = block[1].split("\n- entity ", 1)[0]
        return (f'"sensor{cam["sensor"]}":0 [ENABLED,DYNAMIC]' in block and
                '"mtk-cam camsv-0":0 [ENABLED,DYNAMIC]' in block)
    back, wide = active("back"), active("wide")
    return "back" if back and not wide else "wide" if wide and not back else None


def select_route(target: str, run=subprocess.run) -> str | None:
    """Switch CAMSV-0 to `target`; None on success, else the reason."""
    now = current_route(run)
    if now == target:
        return None
    if now is None:
        return "camera route unknown or partial; refusing to switch"
    links = ([_link(l, False) for l in reversed(CAMERAS[now]["links"])] +
             [_link(l, True) for l in CAMERAS[target]["links"]])
    for spec in links:
        try:
            r = run([MEDIA_CTL, "-d", MEDIA, "-l", spec], capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError) as exc:
            return f"route link {spec} failed: {type(exc).__name__}"
        if r.returncode != 0:
            return f"route link {spec} failed: {(r.stderr or '')[-100:]}"
    return None if current_route(run) == target else f"route to {target} not verified"


class CameraBusy(RuntimeError):
    pass


def disabled() -> str | None:
    for switch in DISABLE:
        if switch.exists():
            return f"camera disabled by {switch}"
    return None


def clean_label(label: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", str(label).strip().lower()).strip("_")[:32] or "unknown"


def items_text(objects: list[dict]) -> str:
    """'laptop(0.75)/person(0.87)' - the camera line's free text."""
    return "/".join(f"{clean_label(o.get('label'))}({float(o.get('confidence', 0)):.2f})"
                    for o in objects[:16])


class _Lock:
    def __init__(self, wait_s: float):
        self.wait_s, self.fh = wait_s, None

    def __enter__(self):
        LOCK.parent.mkdir(parents=True, exist_ok=True)
        self.fh = open(LOCK, "a+")
        deadline = time.monotonic() + self.wait_s
        while True:
            try:
                fcntl.flock(self.fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    self.fh.close()
                    raise CameraBusy("camera is in use") from None
                time.sleep(0.2)

    def __exit__(self, *exc):
        try:
            fcntl.flock(self.fh, fcntl.LOCK_UN)
        finally:
            self.fh.close()


_FW_OK: bool | None = None


def firmware_ready() -> str | None:
    """None if the staged stock firmware is present and intact, else the reason."""
    global _FW_OK
    if _FW_OK:
        return None
    import hashlib
    for name, sha in FW_FILES.items():
        f = FW_DIR / name
        try:
            if hashlib.sha256(f.read_bytes()).hexdigest() != sha:
                return f"camera firmware {f} has the wrong checksum"
        except OSError:
            return f"camera firmware {f} missing"
    _FW_OK = True
    return None


def capture(run=subprocess.run, camera: str = "back") -> tuple[bytes | None, str]:
    """One raw frame, or (None, honest reason). The frame file never outlives this call.
    A wide look switches the route to the IMX355 and always switches back."""
    if camera == "back":
        return _capture(run, CAMERAS["back"])
    why = select_route(camera, run)
    if why:
        select_route("back", run)
        return None, why
    try:
        return _capture(run, CAMERAS[camera])
    finally:
        back_why = select_route("back", run)
        _set_format(run, CAMERAS["back"])
        if back_why:
            print(f"lynx-camera: WARNING route not restored to back: {back_why}", flush=True)


def _set_format(run, cam) -> str | None:
    try:
        fmt = run([V4L2_CTL, "-d", str(DEVICE),
                   f"--set-fmt-video=width={cam['w']},height={cam['h']},pixelformat=BA81"],
                  capture_output=True, text=True, timeout=10)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return f"capture format step failed: {type(exc).__name__}"
    return None if fmt.returncode == 0 else f"capture format not applied: {(fmt.stderr or '')[-120:]}"


def _capture(run, cam) -> tuple[bytes | None, str]:
    if not DEVICE.exists():
        return None, f"{DEVICE} absent: camera stack not prepared for this boot"
    if not Path(CAPTURE).is_file():
        return None, f"capture helper {CAPTURE} not installed"
    why = firmware_ready()
    if why:
        return None, why
    try:
        before = FW_PATH.read_text().strip()
    except OSError as exc:
        return None, f"firmware path unreadable: {exc}"
    if before != FW_DEFAULT:
        return None, f"unexpected firmware path {before!r}; refusing to capture"
    why = _set_format(run, cam)
    if why:
        return None, why
    FRAME.unlink(missing_ok=True)
    try:
        FW_PATH.write_text(str(FW_DIR))
        try:
            proc = run(["/usr/bin/python3", CAPTURE, "--sensor", str(cam["sensor"]), "--settle-ms", str(SETTLE_MS),
                        "--output", str(FRAME)],
                       capture_output=True, text=True, timeout=CAPTURE_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            FRAME.unlink(missing_ok=True)
            return None, f"capture helper timed out after {CAPTURE_TIMEOUT_S:.0f} s"
    finally:
        try:
            FW_PATH.write_text(FW_DEFAULT)   # always put the kernel's firmware path back
        except OSError:
            pass
    try:
        report = json.loads((proc.stdout or "").strip().splitlines()[-1])
    except (ValueError, IndexError):
        report = {}
    try:
        if proc.returncode != 0 or report.get("state") != "frame_captured":
            return None, f"capture failed: {report.get('error') or (proc.stderr or '')[-160:] or proc.returncode}"
        raw = FRAME.read_bytes()
    except OSError as exc:
        return None, f"frame unreadable: {exc}"
    finally:
        FRAME.unlink(missing_ok=True)
    if len(raw) != cam["w"] * cam["h"]:
        return None, f"frame has {len(raw)} bytes, expected {cam['w'] * cam['h']}"
    return raw, "captured"


def detect(raw: bytes, opener=urllib.request.urlopen, w: int = WIDTH, h: int = HEIGHT) -> tuple[list[dict] | None, str]:
    req = urllib.request.Request(f"{DETECT_URL}?w={w}&h={h}", data=raw, method="POST",
                                 headers={"Content-Type": "application/octet-stream"})
    try:
        with opener(req, timeout=DETECT_TIMEOUT_S) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return None, f"Nexus detection refused the frame: HTTP {exc.code}"
    except (OSError, ValueError) as exc:
        return None, f"Nexus detection unreachable: {type(exc).__name__}"
    if not body.get("model_loaded", True):
        return None, "Nexus detector has no model loaded"
    objects = [o for o in body.get("objects", []) if isinstance(o, dict)]
    return sorted(objects, key=lambda o: -float(o.get("confidence", 0))), "detected"


def look(wait_s: float = 0.0, run=subprocess.run, opener=urllib.request.urlopen,
         camera: str = "back") -> dict:
    """One look. {"ok": bool, "objects": [...], "items": "a(0.9)/b(0.5)", "error": str}."""
    reason = disabled()
    if reason:
        return {"ok": False, "error": reason, "busy": False}
    t0 = time.monotonic()
    try:
        with _Lock(wait_s):
            if camera not in CAMERAS:
                return {"ok": False, "error": f"unknown camera {camera!r}", "busy": False}
            raw, why = capture(run=run, camera=camera)
    except CameraBusy as exc:
        return {"ok": False, "error": str(exc), "busy": True}
    if raw is None:
        return {"ok": False, "error": why, "busy": False}
    objects, why = detect(raw, opener=opener, w=CAMERAS[camera]["w"], h=CAMERAS[camera]["h"])
    if objects is None:
        return {"ok": False, "error": why, "busy": False}
    return {"ok": True, "camera": camera, "objects": objects, "items": items_text(objects),
            "labels": [clean_label(o.get("label")) for o in objects],
            "elapsed_s": round(time.monotonic() - t0, 2)}
