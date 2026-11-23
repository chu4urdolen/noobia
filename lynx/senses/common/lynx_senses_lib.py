"""Shared helpers for Lynx's sense emitters (PLAN S2-S5, S8).

Every sense on Lynx is a small, stdlib-only, bounded one-shot program that
lives in ``/usr/local/lib/noobia/senses/<sense>/`` after install (IS-2).
They all share this module (``/usr/local/lib/noobia/senses/common/``) so
the canonical sense-line formatter, the lynx-status snapshot, the state
files, and the honest error shape have exactly one implementation.

Conventions (documented, Aigel-style: defaults, configurable, honest):

- A sense line is ALWAYS built with ``common/autonomy/sense.py``
  (``format_line``/``emit``) imported from the installed autonomy dir;
  if that module is missing the sense fails honestly instead of
  duplicating the format (drift risk).
- One-shot semantics: read the world, compare with the last state, emit
  on transitions or threshold crossings only, persist state atomically,
  and print ONE JSON object to stdout (agent-facing tool convention).
  ``--dry-run`` prints the would-be sense lines and never touches syslog.
- Failures are honest: ``{"ok": false, "error": ..., "detail": ...}`` and
  exit 1. A sense never invents an event it did not observe.
- State lives under ``/var/lib/noobia/senses/<sense>/`` (env
  ``NOOBIA_SENSES_STATE_DIR``), one JSON file per sense, written
  atomically (tmp + rename).
- The ``noobia-agent`` view (S5) is NOT a sense: it never goes through
  this emitter, and the trigger never reads it (loop guard #1).

Environment overrides (defaults are the Lynx install paths):
  NOOBIA_AUTONOMY_DIR   /usr/local/lib/noobia/autonomy
  LYNX_STATUS_BIN       /usr/local/bin/lynx-status
  IW_BIN                /usr/sbin/iw
  LYNX_NOOBD_SOCK       /run/lynx/noobd.sock
  NOOBIA_SENSES_STATE_DIR  /var/lib/noobia/senses
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_AUTONOMY_DIR = "/usr/local/lib/noobia/autonomy"
DEFAULT_STATUS_BIN = "/usr/local/bin/lynx-status"
DEFAULT_IW_BIN = "/usr/sbin/iw"
DEFAULT_NOOBD_SOCK = "/run/lynx/noobd.sock"
DEFAULT_STATE_DIR = "/var/lib/noobia/senses"

# S2 touch (convention, documented): a press is a tap until it outlasts
# this many ms, then it is a hold.
TOUCH_HOLD_MS = 800

# S3 wifi (Aigel's warn convention: weak signal warns, link loss fails).
WIFI_RSSI_LOW_DBM = -75      # at or below this: emit rssi.low (P3)
WIFI_RSSI_REARM_DBM = -70    # back to at least this: re-arm the warning
WIFI_IFACE = "wlan0"

# S4 power (Aigel's warn/fail convention, from aigel/config.json style).
POWER_CRITICAL_PCT = 15      # at or below: battery.critical (P1)
POWER_CRITICAL_REARM_PCT = 20
POWER_LOW_PCT = 30           # at or below: battery.low (P3)
POWER_LOW_REARM_PCT = 35
POWER_THERMAL_HOT_mC = 50000  # at or above: thermal.hot (Tom 2026-11-22: 50 C)
POWER_THERMAL_REARM_mC = 45000
POWER_CHARGE_MA = 50         # deadband: >= +50 mA charging, <= -50 discharging
POWER_SAMPLE_EVERY = 15      # one P0 status.sample per this many samples

# S8 nexus (routing fallback visibility).
NEXUS_DEFAULT_HOST = "192.168.100.106"
NEXUS_DEFAULT_PORT = 8080
NEXUS_FAIL_BEFORE_UNREACHABLE = 2  # consecutive failures before the P1
NEXUS_PROBE_TIMEOUT_S = 3.0


class SenseUnavailable(Exception):
    """The canonical sense module (common/autonomy/sense.py) is not
    installed where this host expects it. Honest, expected on a host
    where the autonomy harness has not been installed yet."""


def import_sense() -> "module":
    """Import the canonical sense formatter from the installed autonomy
    dir (env NOOBIA_AUTONOMY_DIR). Never duplicate format_line: if it is
    missing, fail loudly and honestly instead of drifting."""
    directory = os.environ.get("NOOBIA_AUTONOMY_DIR", DEFAULT_AUTONOMY_DIR)
    path = Path(directory) / "sense.py"
    if not path.is_file():
        raise SenseUnavailable(
            f"canonical sense module not found at {path}; the autonomy "
            f"harness install (IS-2) is missing or NOOBIA_AUTONOMY_DIR is wrong")
    spec = importlib.util.spec_from_file_location("noobia_sense", path)
    if spec is None or spec.loader is None:
        raise SenseUnavailable(f"could not load sense module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def clean_field(value: object) -> str:
    """Sanitize a value into a legal sense-line field value
    (ASCII, no whitespace, no quotes, no pipes, <= 32 chars)."""
    text = str(value)
    if not text.isascii():
        text = text.encode("ascii", "replace").decode("ascii")
    text = re.sub(r"[\s\"'|]+", "_", text)
    return text[:32]


def clean_text(value: object) -> str:
    """Sanitize a value into a legal sense-line text tail (<= 300 chars,
    one line). Non-ASCII is allowed; format_line bounds the bytes."""
    text = str(value)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:300]


# Tom, 2026-11-23/24: "put priority 5 on all" lines. Five P5 lines of any
# kind close an autonomy chunk; fewer wait for its 15 s window. 0 keeps each
# sense's own priority (the unit tests use that to check sense meanings).
REACTION_PRIORITY = int(os.environ.get("LYNX_REACTION_PRIORITY", "5"))


def emit_line(sense_mod, p: int, sense: str, event: str,
              fields: dict | None = None, text: str = "",
              dry_run: bool = False) -> str:
    """Format a canonical line and emit it (syslog) unless dry_run.
    Returns the canonical line. Raises ValueError on bad inputs - the
    caller reports that honestly and emits nothing."""
    fields = {clean_field(k): clean_field(v) for k, v in (fields or {}).items()}
    if REACTION_PRIORITY >= 1:
        p = REACTION_PRIORITY   # Tom 2026-11-24: every line is P5, status samples too
    line = sense_mod.format_line(p, sense, event, fields=fields or None,
                                 text=clean_text(text))
    if not dry_run:
        sense_mod.emit(p, sense, event, fields=fields or None,
                       text=clean_text(text))
    return line


# -- state files -------------------------------------------------------------

def state_path(sense: str, override: str | None = None) -> Path:
    if override:
        return Path(override)
    root = Path(os.environ.get("NOOBIA_SENSES_STATE_DIR", DEFAULT_STATE_DIR))
    return root / sense / "state.json"


# Gwyn 2026-11-22: the senses loop samples motion every second and touch every
# 2 s; writing every sample's state to flash cost hundreds of MB a day. The
# loop is one long-lived process, so the newest state lives in memory and the
# file is rewritten only when a meaningful field changed or once a minute.
# Fields that change on every sample and matter only as counters:
VOLATILE_STATE_KEYS = frozenset({"samples", "t", "last_ts", "last_raw", "queued", "dropped",
                                 "last_cap", "last_soc_mC", "temp_check_t",
                                 "tilts", "still_since"})   # motion gesture history (RAM)
STATE_FLUSH_S = 60.0
_STATE_CACHE: dict = {}   # str(path) -> (data, last disk write monotonic, written stable view)


def _stable(data: dict) -> dict:
    return {k: v for k, v in data.items() if k not in VOLATILE_STATE_KEYS}


def load_state(path: Path) -> dict:
    cached = _STATE_CACHE.get(str(path))
    if cached is not None:
        return json.loads(json.dumps(cached[0]))  # a private copy
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(path: Path, data: dict) -> None:
    key, now = str(path), time.monotonic()
    snapshot = json.loads(json.dumps(data))
    stable = _stable(snapshot)
    cached = _STATE_CACHE.get(key)
    if cached is not None and cached[2] == stable and now - cached[1] < STATE_FLUSH_S:
        _STATE_CACHE[key] = (snapshot, cached[1], cached[2])
        return
    _write_state(path, data)
    _STATE_CACHE[key] = (snapshot, now, stable)


def _write_state(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, sort_keys=True, separators=(",", ":"))
    os.replace(tmp, path)


# -- bounded reads of Lynx ----------------------------------------------------

def run_cmd(argv: list[str], timeout: float = 8.0) -> tuple[int | None, str]:
    """Run one bounded command (no shell). Returns (rc, stdout) or
    (None, '') on spawn/timeout trouble."""
    try:
        result = subprocess.run(argv, capture_output=True, text=True,
                                timeout=timeout, check=False)
        return result.returncode, result.stdout
    except (OSError, subprocess.TimeoutExpired):
        return None, ""


def lynx_status(status_bin: str | None = None,
                timeout: float = 8.0) -> dict:
    """Run /usr/local/bin/lynx-status (schema 2) and parse its JSON.
    Raises LookupError when the snapshot cannot be trusted."""
    binary = status_bin or os.environ.get("LYNX_STATUS_BIN", DEFAULT_STATUS_BIN)
    rc, out = run_cmd([binary], timeout=timeout)
    if rc != 0:
        raise LookupError(f"lynx-status exited {rc}")
    try:
        data = json.loads(out)
    except ValueError as exc:
        raise LookupError(f"lynx-status did not return JSON: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema") != 2:
        raise LookupError(f"lynx-status schema is {data.get('schema') if isinstance(data, dict) else '?'}, expected 2")
    return data


_IW_LINK = re.compile(r"signal:\s*(-?\d+)\s*dBm", re.M)
_IW_CONNECTED = re.compile(r"Connected to\s+([0-9a-f:]+)\s*\(on\s+(\w+)\)")
_IW_SSID = re.compile(r"SSID:\s*(\S+)")


def iw_link(iw_bin: str | None = None, iface: str = WIFI_IFACE,
            timeout: float = 5.0) -> dict:
    """Read the Wi-Fi link quality via `iw dev <iface> link` (bounded,
    read-only). Returns {connected, iface, signal_dbm, ssid}; signal_dbm
    is None when the interface is not associated or the read failed."""
    binary = iw_bin or os.environ.get("IW_BIN", DEFAULT_IW_BIN)
    rc, out = run_cmd([binary, "dev", iface, "link"], timeout=timeout)
    result = {"connected": False, "iface": iface, "signal_dbm": None,
              "ssid": None}
    if rc not in (0, 1) or not out:
        return result
    conn = _IW_CONNECTED.search(out)
    sig = _IW_LINK.search(out)
    ssid = _IW_SSID.search(out)
    result["connected"] = bool(conn)
    if conn:
        result["iface"] = conn.group(2)
    if sig:
        result["signal_dbm"] = int(sig.group(1))
    if ssid:
        result["ssid"] = ssid.group(1)
    return result


# -- touch (S2): NRP/1 TOUCH_STATUS, non-consuming -----------------------------

TOUCH_RE = re.compile(r"NRP/1 7 OK value=(-?\d+)(?: detail=([^\r\n]*))?\Z")
TOUCH_DETAIL = re.compile(r"panel=(\S+) down=([01]) queued=(\d+) dropped=(\d+)\Z")


def nrp_touch_status(sock_path: str | None = None, timeout: float = 2.0) -> dict:
    """Read the runtime's touch queue state (TOUCH_STATUS, 380) over the
    local NRP socket. Non-consuming: never sends TOUCH_POLL (381), which
    is the only popper of the shared 8-slot queue (design doc
    LYNX-TOUCH-EVENTS-DESIGN-20261121.md). Raises on any surprise."""
    import socket
    path = sock_path or os.environ.get("LYNX_NOOBD_SOCK", DEFAULT_NOOBD_SOCK)
    with socket.socket(socket.AF_UNIX) as conn:
        conn.settimeout(timeout)
        conn.connect(path)
        conn.sendall(b"NRP/1 7 CALL TOUCH_STATUS\n")
        with conn.makefile("rb") as stream:
            data = b""
            for _ in range(4):
                data = stream.readline(4097)
                if not data.startswith(b"NRP/1 0 EVENT "):
                    break
    if len(data) > 4096 or not data.endswith(b"\n"):
        raise RuntimeError("incomplete NRP reply")
    reply = data.decode("ascii").rstrip("\n")
    match = TOUCH_RE.fullmatch(reply)
    if match is None:
        raise RuntimeError("TOUCH_STATUS call failed")
    detail = TOUCH_DETAIL.fullmatch(match.group(2) or "")
    if detail is None:
        raise RuntimeError("unexpected TOUCH_STATUS detail")
    queued, dropped = int(detail.group(3)), int(detail.group(4))
    if queued > 8:
        raise RuntimeError("queue count exceeds runtime capacity")
    return {"panel_open": match.group(1) == "1",
            "finger_down": detail.group(2) == "1",
            "queued": queued, "dropped": dropped}


# -- output helpers ------------------------------------------------------------

def json_out(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def finish(result: dict, code: int) -> int:
    print(json_out(result))
    return code


def base_result(sense: str, **extra) -> dict:
    result = {"ok": True, "sense": sense}
    result.update(extra)
    return result


def failure(sense: str, exc: Exception) -> tuple[dict, int]:
    return ({"ok": False, "sense": sense,
             "error": type(exc).__name__,
             "detail": str(exc)[:200]}, 1)


def now_ts() -> int:
    return int(time.time())
