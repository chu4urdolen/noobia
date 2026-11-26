#!/usr/bin/env python3
"""Noobia MCP Server - Model Context Protocol for Noobia devices and Argus.

Standardizes remote and local access across Noobia hardware:
- Replaces home-grown DIY json-stdin manifests and custom wrappers with standard MCP tools.
- Bridges to remote Noobs over Wi-Fi (NRP/1 on TCP 4243), Bluetooth (BLE GATT), or local daemons.
- Implements standard MCP (JSON-RPC 2.0) over stdio for AI assistants (Antigravity, Claude Code, etc.).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

ROOT = Path("/noobia")
LYNX_TOOLS = ROOT / "lynx" / "tools"
IRIS_TOOLS = ROOT / "iris" / "tools"
ROSE_CALLS = ROOT / "rose" / "calls"
ARGUS_TOOLS = Path(os.environ.get("NOOBIA", "/noobia")) / "argus" / "tools"
LOCAL_CALLS = LYNX_TOOLS / "local_calls"

# Regex pattern for valid tool names
NAME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$")


def load_native_mcp_tools(directory: str | Path) -> Dict[str, Tuple[Optional[Path], Dict[str, Any]]]:
    """Scan a directory for native MCP tool manifests (*.json) and optional matching scripts (*.sh)."""
    dir_path = Path(directory)
    if not dir_path.is_dir():
        return {}
    tools = {}
    for manifest_path in sorted(dir_path.glob("*.json")):
        name = manifest_path.stem
        if not NAME_PATTERN.match(name):
            continue
        script_path = manifest_path.with_suffix(".sh")
        if script_path.is_symlink() or not script_path.is_file():
            script_path = None
        try:
            meta = json.loads(manifest_path.read_text(encoding="utf-8"))
            tool_name = meta.get("name", name)
            input_schema = meta.get("inputSchema") or meta.get("parameters", {
                "type": "object", "properties": {}, "additionalProperties": False
            })
            mcp_spec = {
                "name": tool_name,
                "description": meta.get("description", f"Noobia tool: {tool_name}"),
                "inputSchema": input_schema,
            }
            if "timeout" in meta:
                mcp_spec["timeout"] = meta["timeout"]
            tools[tool_name] = (script_path, mcp_spec)
        except Exception:
            continue
    return tools

# Import Lynx auth if available
sys.path.insert(0, str(LYNX_TOOLS))
try:
    from lynx_ble_auth import envelope, load_key  # type: ignore
except ImportError:
    envelope, load_key = None, None

LYNX_HOST = "192.168.100.107"
LYNX_PORT = 4243
LYNX_SSH_PORT = 2222
LYNX_KEY_PATH = ROOT / "lynx" / "private" / "nrp-nexus.key"


# -----------------------------------------------------------------------------
# Low-Level NRP/1 Remote Clients
# -----------------------------------------------------------------------------

def lynx_nrp_command(command: str, timeout: float = 8.0) -> str:
    """Send an NRP/1 command to Lynx over authenticated Wi-Fi TCP link."""
    if not command.isascii() or "\n" in command or "\r" in command:
        raise ValueError("Command must be a single-line ASCII string")

    if envelope is None or load_key is None or not LYNX_KEY_PATH.exists():
        # Fallback to lynx_noobctl.py subprocess if available
        ctl = LYNX_TOOLS / "lynx_noobctl.py"
        if ctl.is_file():
            res = subprocess.run(
                [sys.executable, str(ctl)] + command.split(),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            if res.returncode == 0:
                return res.stdout.strip()
            raise RuntimeError(f"lynx_noobctl failed: {res.stderr.strip() or res.stdout.strip()}")
        raise RuntimeError("Lynx authentication key not found")

    key = load_key(str(LYNX_KEY_PATH))
    with socket.create_connection((LYNX_HOST, LYNX_PORT), timeout=min(timeout, 4.0)) as conn:
        conn.settimeout(timeout)
        with conn.makefile("rb") as stream:
            challenge = stream.readline(129)
            match = re.fullmatch(rb"AUTH/1 CHALLENGE ([0-9a-f]{64})\n", challenge)
            if not match:
                raise RuntimeError("Lynx did not present an authentication challenge")
            request = f"NRP/1 1 {command}\n".encode("ascii")
            conn.sendall(
                envelope(key, bytes.fromhex(match.group(1).decode()), 1, request, max_frame=4096)
            )
            while True:
                line = stream.readline(4097)
                if not line.endswith(b"\n"):
                    raise RuntimeError("Incomplete or oversized reply from Lynx")
                answer = line.decode("ascii", errors="replace").rstrip("\n")
                if not answer.startswith("NRP/1 0 EVENT "):
                    break
            return answer


def iris_nrp_command(command: str, timeout: float = 12.0) -> str:
    """Send an NRP/1 command to Iris via irisctl / BLE bridge."""
    irisctl = IRIS_TOOLS / "irisctl"
    if not irisctl.is_file():
        raise RuntimeError("irisctl tool not found")

    res = subprocess.run(
        ["/bin/bash", str(irisctl)] + command.split(),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if res.returncode == 0:
        return res.stdout.strip()
    err = res.stderr.strip() or res.stdout.strip()
    raise RuntimeError(f"irisctl command failed: {err}")


# -----------------------------------------------------------------------------
# Built-In MCP Tool Handlers
# -----------------------------------------------------------------------------

def handle_argus(action: str, args: Dict[str, Any]) -> str:
    """Use the authenticated Nexus-to-Argus client; no LAN listener is exposed."""
    if action not in ("status", "collect-day", "ledger", "job-status", "job-result"):
        raise ValueError("invalid Argus action")
    sys.path.insert(0, str(ARGUS_TOOLS))
    from argus_client import call
    return json.dumps(call(action, date=args.get("date"), job_id=args.get("job_id")),
                      ensure_ascii=False)

def _parse_nrp_payload(reply: str) -> Dict[str, Any]:
    """Parse standard NRP/1 reply into structured dict."""
    reply = reply.strip()
    if " OK" in reply:
        data = {"ok": True, "raw": reply}
        val_match = re.search(r"value=(-?\d+)", reply)
        if val_match:
            data["value"] = int(val_match.group(1))
        det_match = re.search(r"detail=(.*)", reply)
        if det_match:
            data["detail"] = det_match.group(1).strip()
            # Check for base64 JSON payload in detail
            b64_match = re.search(r"data=([A-Za-z0-9_-]+)", data["detail"])
            if b64_match:
                try:
                    padded = b64_match.group(1) + "=" * (-len(b64_match.group(1)) % 4)
                    decoded = base64.urlsafe_b64decode(padded).decode("utf-8")
                    data["json_payload"] = json.loads(decoded)
                except Exception:
                    pass
        return data
    elif " ERR" in reply:
        return {"ok": False, "error": reply, "raw": reply}
    return {"ok": True, "raw": reply}


# Lynx handlers
def handle_lynx_ping(args: Dict[str, Any]) -> str:
    ans = lynx_nrp_command("PING")
    return json.dumps(_parse_nrp_payload(ans))


def handle_lynx_status(args: Dict[str, Any]) -> str:
    """Get full Lynx system and hardware status over SSH helper."""
    helper = LYNX_TOOLS / "lynx_remote.py"
    res = subprocess.run(
        [sys.executable, str(helper), "run", "/usr/local/bin/lynx-status", "--timeout", "5"],
        capture_output=True,
        text=True,
        timeout=8,
        check=False,
    )
    if res.returncode != 0:
        return json.dumps({"ok": False, "error": res.stderr.strip() or res.stdout.strip()})
    lines = res.stdout.strip().split("\n")
    # First line is exit=0, remainder is JSON
    payload = "\n".join(lines[1:]) if len(lines) > 1 and lines[0].startswith("exit=") else res.stdout
    try:
        return json.dumps({"ok": True, "status": json.loads(payload)})
    except Exception:
        return json.dumps({"ok": True, "raw": payload})


def handle_lynx_caps(args: Dict[str, Any]) -> str:
    ans = lynx_nrp_command("CAPS")
    return json.dumps(_parse_nrp_payload(ans))


def handle_lynx_battery(args: Dict[str, Any]) -> str:
    pct = _parse_nrp_payload(lynx_nrp_command("CALL BATTERY_PERCENT"))
    temp = _parse_nrp_payload(lynx_nrp_command("CALL BATTERY_TEMP"))
    curr = _parse_nrp_payload(lynx_nrp_command("CALL BATTERY_CURRENT"))
    volt = _parse_nrp_payload(lynx_nrp_command("CALL BATTERY_VOLTAGE"))
    return json.dumps({
        "ok": pct.get("ok", False) and temp.get("ok", False),
        "capacity_percent": pct.get("value"),
        "temperature_celsius": (temp.get("value") / 1000.0) if temp.get("value") is not None else None,
        "current_mA": curr.get("value"),
        "voltage_mV": volt.get("value"),
    })


def handle_lynx_camera_status(args: Dict[str, Any]) -> str:
    ans = lynx_nrp_command("CALL CAMERA_STATUS")
    return json.dumps(_parse_nrp_payload(ans))


def handle_lynx_flashlight_pulse(args: Dict[str, Any]) -> str:
    duration = int(args.get("duration_ms", 50))
    if not 20 <= duration <= 100:
        raise ValueError("duration_ms must be between 20 and 100 ms")
    ans = lynx_nrp_command(f"CALL FLASH_PULSE {duration}")
    return json.dumps(_parse_nrp_payload(ans))


def handle_lynx_flashlight_stop(args: Dict[str, Any]) -> str:
    ans = lynx_nrp_command("CALL FLASH_STOP")
    return json.dumps(_parse_nrp_payload(ans))


def handle_lynx_microphone_level(args: Dict[str, Any]) -> str:
    ans = lynx_nrp_command("CALL MIC_LEVEL", timeout=12.0)
    return json.dumps(_parse_nrp_payload(ans))


def handle_lynx_haptic_set(args: Dict[str, Any]) -> str:
    duration = int(args.get("duration_ms", 80))
    bit = 1 if args.get("activate", True) else 0
    ans = lynx_nrp_command(f"CALL HAPTIC_SET {duration} {bit}")
    return json.dumps(_parse_nrp_payload(ans))


def handle_lynx_haptic_stop(args: Dict[str, Any]) -> str:
    ans = lynx_nrp_command("CALL HAPTIC_STOP")
    return json.dumps(_parse_nrp_payload(ans))


def handle_lynx_motion(args: Dict[str, Any]) -> str:
    ans = lynx_nrp_command("CALL ACCEL_VECTOR")
    return json.dumps(_parse_nrp_payload(ans))


def handle_lynx_magnetometer(args: Dict[str, Any]) -> str:
    ans = lynx_nrp_command("CALL MAG_VECTOR")
    return json.dumps(_parse_nrp_payload(ans))


def handle_lynx_light(args: Dict[str, Any]) -> str:
    ans = lynx_nrp_command("CALL LIGHT_RAW")
    return json.dumps(_parse_nrp_payload(ans))


def handle_lynx_proximity(args: Dict[str, Any]) -> str:
    ans = lynx_nrp_command("CALL PROX_RAW")
    return json.dumps(_parse_nrp_payload(ans))


def handle_lynx_queue_health(args: Dict[str, Any]) -> str:
    ans = lynx_nrp_command("CALL_TEXT LYNX_QUEUE_HEALTH {}")
    return json.dumps(_parse_nrp_payload(ans))


def handle_lynx_agent_health(args: Dict[str, Any]) -> str:
    ans = lynx_nrp_command("CALL LYNX_AGENT_HEALTH")
    return json.dumps(_parse_nrp_payload(ans))


def handle_lynx_raw_nrp(args: Dict[str, Any]) -> str:
    cmd = args.get("command", "").strip()
    if not cmd:
        raise ValueError("command is required")
    ans = lynx_nrp_command(cmd)
    return json.dumps(_parse_nrp_payload(ans))


# Iris handlers
def handle_iris_status(args: Dict[str, Any]) -> str:
    ans = iris_nrp_command("status")
    return json.dumps({"ok": True, "status": ans})


def handle_iris_ping(args: Dict[str, Any]) -> str:
    ans = iris_nrp_command("ping")
    return json.dumps(_parse_nrp_payload(ans))


def handle_iris_caps(args: Dict[str, Any]) -> str:
    ans = iris_nrp_command("caps")
    return json.dumps(_parse_nrp_payload(ans))


def handle_iris_camera_capture(args: Dict[str, Any]) -> str:
    ans = iris_nrp_command("capture")
    return json.dumps(_parse_nrp_payload(ans))


def handle_iris_storage_status(args: Dict[str, Any]) -> str:
    ans = iris_nrp_command("call STORAGE_STATUS")
    return json.dumps(_parse_nrp_payload(ans))


def handle_iris_mic_level(args: Dict[str, Any]) -> str:
    ans = iris_nrp_command("mic-level")
    return json.dumps(_parse_nrp_payload(ans))


def handle_iris_led_rgb(args: Dict[str, Any]) -> str:
    r = int(args.get("red", 0))
    g = int(args.get("green", 0))
    b = int(args.get("blue", 0))
    ans = iris_nrp_command(f"led {r} {g} {b}")
    return json.dumps(_parse_nrp_payload(ans))


def handle_iris_wifi_status(args: Dict[str, Any]) -> str:
    ans = iris_nrp_command("wifi-status")
    return json.dumps(_parse_nrp_payload(ans))


def handle_iris_time_now(args: Dict[str, Any]) -> str:
    ans = iris_nrp_command("time-now")
    return json.dumps(_parse_nrp_payload(ans))


def handle_iris_raw_nrp(args: Dict[str, Any]) -> str:
    cmd = args.get("command", "").strip()
    if not cmd:
        raise ValueError("command is required")
    ans = iris_nrp_command(cmd)
    return json.dumps(_parse_nrp_payload(ans))


# -----------------------------------------------------------------------------
# Tool Catalog Definition
# -----------------------------------------------------------------------------

BUILTIN_TOOLS: List[Tuple[Dict[str, Any], Callable[[Dict[str, Any]], str]]] = [
    (
        {"name": "argus_status", "description": "Entity: Argus. Read historian evidence and job health.",
         "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
        lambda args: handle_argus("status", args),
    ),
    (
        {"name": "argus_collect_day", "description": "Entity: Argus. Sync Forge evidence and queue a dated ledger; returns a job ID.",
         "inputSchema": {"type": "object", "properties": {"date": {"type": "string", "description": "Europe/Sofia date, YYYY-MM-DD; defaults to today"}}, "additionalProperties": False}},
        lambda args: handle_argus("collect-day", args),
    ),
    (
        {"name": "argus_daily_ledger", "description": "Entity: Argus. Read the latest evidence ledger for a date.",
         "inputSchema": {"type": "object", "properties": {"date": {"type": "string"}},
                         "required": ["date"], "additionalProperties": False}},
        lambda args: handle_argus("ledger", args),
    ),
    (
        {"name": "argus_job_status", "description": "Entity: Argus. Read a named historian job state.",
         "inputSchema": {"type": "object", "properties": {"job_id": {"type": "string"}},
                         "required": ["job_id"], "additionalProperties": False}},
        lambda args: handle_argus("job-status", args),
    ),
    (
        {"name": "argus_job_result", "description": "Entity: Argus. Read a completed historian job result.",
         "inputSchema": {"type": "object", "properties": {"job_id": {"type": "string"}},
                         "required": ["job_id"], "additionalProperties": False}},
        lambda args: handle_argus("job-result", args),
    ),
    # Lynx Tools
    (
        {
            "name": "lynx_ping",
            "description": "Entity: Lynx. Test remote NRP/1 connectivity over Wi-Fi / TCP link.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        handle_lynx_ping,
    ),
    (
        {
            "name": "lynx_status",
            "description": "Entity: Lynx. Read full system health, battery, WiFi IP, thermal zones, and running services.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        handle_lynx_status,
    ),
    (
        {
            "name": "lynx_caps",
            "description": "Entity: Lynx. Query remote NRP/1 protocol capabilities and registered native functions.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        handle_lynx_caps,
    ),
    (
        {
            "name": "lynx_battery",
            "description": "Entity: Lynx. Read battery percentage, temperature, charging current, and voltage.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        handle_lynx_battery,
    ),
    (
        {
            "name": "lynx_camera_status",
            "description": "Entity: Lynx. Read camera hardware interface status and sensor validation state.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        handle_lynx_camera_status,
    ),
    (
        {
            "name": "lynx_flashlight_pulse",
            "description": "Entity: Lynx. Trigger a safe, bounded flashlight pulse (20-100 ms) with OFF verification.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "duration_ms": {
                        "type": "integer",
                        "minimum": 20,
                        "maximum": 100,
                        "description": "Pulse duration in milliseconds (default 50)",
                    }
                },
                "additionalProperties": False,
            },
        },
        handle_lynx_flashlight_pulse,
    ),
    (
        {
            "name": "lynx_flashlight_stop",
            "description": "Entity: Lynx. Explicitly turn off flashlight LED.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        handle_lynx_flashlight_stop,
    ),
    (
        {
            "name": "lynx_microphone_level",
            "description": "Entity: Lynx. Sample microphone acoustic level for 1 second; returns RMS x 100. Does not record audio.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        handle_lynx_microphone_level,
    ),
    (
        {
            "name": "lynx_haptic_set",
            "description": "Entity: Lynx. Vibrate haptic motor for duration_ms (20-250 ms) with automatic cooldown.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "duration_ms": {
                        "type": "integer",
                        "minimum": 20,
                        "maximum": 250,
                        "description": "Vibration pulse duration in ms (default 80)",
                    },
                    "activate": {
                        "type": "boolean",
                        "description": "True to activate, False to stop",
                    },
                },
                "additionalProperties": False,
            },
        },
        handle_lynx_haptic_set,
    ),
    (
        {
            "name": "lynx_haptic_stop",
            "description": "Entity: Lynx. Stop haptic vibration motor immediately.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        handle_lynx_haptic_stop,
    ),
    (
        {
            "name": "lynx_motion_read",
            "description": "Entity: Lynx. Read raw Bosch accelerometer 3-axis motion vector (X, Y, Z).",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        handle_lynx_motion,
    ),
    (
        {
            "name": "lynx_magnetometer_read",
            "description": "Entity: Lynx. Read raw AKM magnetometer 3-axis magnetic field vector (X, Y, Z).",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        handle_lynx_magnetometer,
    ),
    (
        {
            "name": "lynx_light_read",
            "description": "Entity: Lynx. Read raw ambient optical sensor level.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        handle_lynx_light,
    ),
    (
        {
            "name": "lynx_proximity_read",
            "description": "Entity: Lynx. Read raw AMS proximity sensor event.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        handle_lynx_proximity,
    ),
    (
        {
            "name": "lynx_queue_health",
            "description": "Entity: Lynx. Check local agent job queue counts, status, and pending items.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        handle_lynx_queue_health,
    ),
    (
        {
            "name": "lynx_agent_health",
            "description": "Entity: Lynx. Check status of on-device agent daemon.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        handle_lynx_agent_health,
    ),
    (
        {
            "name": "lynx_raw_nrp",
            "description": "Entity: Lynx. Execute an arbitrary bounded NRP/1 line command over Wi-Fi link.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "e.g. CALL HAPTIC_STATUS"}
                },
                "required": ["command"],
                "additionalProperties": False,
            },
        },
        handle_lynx_raw_nrp,
    ),
    # Iris Tools
    (
        {
            "name": "iris_status",
            "description": "Entity: Iris (ESP32 Camera). Check BLE bridge connection status.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        handle_iris_status,
    ),
    (
        {
            "name": "iris_ping",
            "description": "Entity: Iris. Send NRP/1 PING to Iris over BLE/serial bridge.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        handle_iris_ping,
    ),
    (
        {
            "name": "iris_caps",
            "description": "Entity: Iris. Query NRP/1 capabilities and functions.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        handle_iris_caps,
    ),
    (
        {
            "name": "iris_camera_capture",
            "description": "Entity: Iris. Trigger camera capture and save image to SD storage.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        handle_iris_camera_capture,
    ),
    (
        {
            "name": "iris_storage_status",
            "description": "Entity: Iris. Check micro-SD card mount and storage status.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        handle_iris_storage_status,
    ),
    (
        {
            "name": "iris_mic_level",
            "description": "Entity: Iris. Sample microphone I2S loudness level.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        handle_iris_mic_level,
    ),
    (
        {
            "name": "iris_led_rgb",
            "description": "Entity: Iris. Set RGB LED values (0-255).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "red": {"type": "integer", "minimum": 0, "maximum": 255},
                    "green": {"type": "integer", "minimum": 0, "maximum": 255},
                    "blue": {"type": "integer", "minimum": 0, "maximum": 255},
                },
                "required": ["red", "green", "blue"],
                "additionalProperties": False,
            },
        },
        handle_iris_led_rgb,
    ),
    (
        {
            "name": "iris_wifi_status",
            "description": "Entity: Iris. Check Wi-Fi connection and signal strength.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        handle_iris_wifi_status,
    ),
    (
        {
            "name": "iris_time_now",
            "description": "Entity: Iris. Read 32-bit monotonic millisecond hardware clock.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        handle_iris_time_now,
    ),
    (
        {
            "name": "iris_raw_nrp",
            "description": "Entity: Iris. Execute an arbitrary bounded NRP/1 command on Iris.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "e.g. self-test"}
                },
                "required": ["command"],
                "additionalProperties": False,
            },
        },
        handle_iris_raw_nrp,
    ),
]


class NoobMCPServer:
    """Standard Model Context Protocol Server for Noobia."""

    def __init__(self, manifest_dirs: Optional[List[Path]] = None):
        self.tools: Dict[str, Dict[str, Any]] = {}
        self.handlers: Dict[str, Callable[[Dict[str, Any]], str]] = {}

        # 1. Register Built-in Remote Tools
        for spec, handler in BUILTIN_TOOLS:
            name = spec["name"]
            self.tools[name] = spec
            self.handlers[name] = handler

        # 2. Register Dynamic Manifest Tools from Directories
        dirs = manifest_dirs if manifest_dirs is not None else [LOCAL_CALLS, ROSE_CALLS]
        for d in dirs:
            dir_path = Path(d)
            if not dir_path.is_dir():
                continue
            is_lynx_dir = (
                dir_path.resolve() == LOCAL_CALLS.resolve()
                or ("lynx" in dir_path.parts and "local_calls" in dir_path.parts)
            )
            loaded = load_native_mcp_tools(dir_path)
            for name, (script, mcp_spec) in loaded.items():
                if name in self.tools:
                    # Built-in takes precedence unless local script is specifically wanted
                    continue
                self.tools[name] = mcp_spec
                if is_lynx_dir:
                    self.handlers[name] = self._make_lynx_remote_script_handler(script, mcp_spec)
                else:
                    self.handlers[name] = self._make_local_script_handler(script, mcp_spec)

    @staticmethod
    def _extract_remote_command(script: Path) -> str:
        text = script.read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("exec "):
                return line[5:].strip()
        return text.strip()

    @classmethod
    def _make_lynx_remote_script_handler(
        cls, script: Optional[Path], meta: Dict[str, Any]
    ) -> Callable[[Dict[str, Any]], str]:
        def handler(args: Dict[str, Any]) -> str:
            if not script or not script.is_file():
                return json.dumps({"ok": False, "error": "No remote script found for tool"})
            remote_cmd = cls._extract_remote_command(script)
            timeout = min(60, max(1, int(meta.get("timeout", 10))))

            # Formulate pinned SSH command
            try:
                from lynx_wifi_v19_contact import ssh_command  # type: ignore
                argv = ssh_command(LYNX_HOST, remote_cmd)
                argv[-2:-2] = ["-p", str(LYNX_SSH_PORT)]
            except Exception:
                argv = [
                    "ssh",
                    "-o", "BatchMode=yes",
                    "-o", "IdentitiesOnly=yes",
                    "-o", "StrictHostKeyChecking=yes",
                    "-o", "GlobalKnownHostsFile=/dev/null",
                    "-o", "HostKeyAlias=lynx",
                    "-o", f"UserKnownHostsFile={ROOT}/lynx/secrets/lynx_known_hosts",
                    "-o", "ConnectTimeout=5",
                    "-i", f"{ROOT}/lynx/secrets/nexus_lynx_ed25519",
                    "-p", str(LYNX_SSH_PORT),
                    f"root@{LYNX_HOST}",
                    remote_cmd,
                ]

            try:
                stdin_data = json.dumps(args) if args else None
                res = subprocess.run(
                    argv,
                    input=stdin_data,
                    capture_output=True,
                    text=True,
                    timeout=timeout + 3,
                    check=False,
                )
                output = res.stdout.strip()
                if res.returncode != 0:
                    err = res.stderr.strip() or f"exit code {res.returncode}"
                    return json.dumps({"ok": False, "exit_code": res.returncode, "error": err})
                try:
                    return json.dumps({"ok": True, "result": json.loads(output)})
                except Exception:
                    return json.dumps({"ok": True, "output": output})
            except subprocess.TimeoutExpired:
                return json.dumps({"ok": False, "error": f"Lynx remote tool execution timed out after {timeout}s"})
            except Exception as exc:
                return json.dumps({"ok": False, "error": str(exc)})

        return handler

    @staticmethod
    def _make_local_script_handler(
        script: Optional[Path], meta: Dict[str, Any]
    ) -> Callable[[Dict[str, Any]], str]:
        def handler(args: Dict[str, Any]) -> str:
            if not script or not script.is_file():
                return json.dumps({"ok": False, "error": "No local executable script for tool"})
            timeout = min(60, max(1, int(meta.get("timeout", 10))))
            env = {
                k: v
                for k, v in os.environ.items()
                if "KEY" not in k.upper() and not k.startswith(("OPENAI_", "NOOBIA_INFERENCE_"))
            }
            try:
                res = subprocess.run(
                    ["/bin/sh", str(script)],
                    input=json.dumps(args),
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    env=env,
                    check=False,
                )
                output = res.stdout.strip()
                if res.returncode != 0:
                    err = res.stderr.strip() or f"exit code {res.returncode}"
                    return json.dumps({"ok": False, "exit_code": res.returncode, "error": err})
                try:
                    return json.dumps({"ok": True, "result": json.loads(output)})
                except Exception:
                    return json.dumps({"ok": True, "output": output})
            except subprocess.TimeoutExpired:
                return json.dumps({"ok": False, "error": "Tool execution timed out"})
            except Exception as exc:
                return json.dumps({"ok": False, "error": str(exc)})

        return handler

    def list_tools(self) -> List[Dict[str, Any]]:
        return list(self.tools.values())

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Tuple[str, bool]:
        """Call an MCP tool by name. Returns (result_text, is_error)."""
        handler = self.handlers.get(name)
        if not handler:
            return f"Error: Tool '{name}' not found", True
        try:
            result = handler(arguments or {})
            return result, False
        except Exception as exc:
            return f"Error executing '{name}': {exc}", True

    def handle_request(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process a single JSON-RPC 2.0 message."""
        msg_id = message.get("id")
        method = message.get("method")

        # Notification without id
        if msg_id is None:
            return None

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "noobia-mcp",
                        "version": "1.0.0",
                        "description": "Unified Noobia MCP server for remote Lynx, Iris, and local tools",
                    },
                },
            }

        elif method == "ping":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": self.list_tools()},
            }

        elif method == "tools/call":
            params = message.get("params", {})
            name = params.get("name")
            arguments = params.get("arguments", {})
            if not name:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32602, "message": "Missing 'name' parameter"},
                }

            text, is_error = self.call_tool(name, arguments)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": text}],
                    "isError": is_error,
                },
            }

        else:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Method '{method}' not found"},
            }

    def run_stdio(self) -> None:
        """Run the JSON-RPC stdio event loop."""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except Exception as exc:
                sys.stdout.write(
                    json.dumps(
                        {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
                    )
                    + "\n"
                )
                sys.stdout.flush()
                continue

            response = self.handle_request(message)
            if response is not None:
                sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
                sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="list all available MCP tools as JSON")
    parser.add_argument("--call", metavar="NAME", help="invoke a tool by name")
    parser.add_argument("--args", default="{}", help="JSON arguments for --call")
    args = parser.parse_args()

    server = NoobMCPServer()

    if args.list:
        tools = server.list_tools()
        print(json.dumps({"count": len(tools), "tools": tools}, indent=2))
        return

    if args.call:
        tool_args = json.loads(args.args)
        output, is_error = server.call_tool(args.call, tool_args)
        print(output)
        if is_error:
            sys.exit(1)
        return

    # Standard stdio server loop
    server.run_stdio()


if __name__ == "__main__":
    main()
