#!/usr/bin/env python3
"""lynx_debug_helper: Debug mode backend for Lynx (Banshee, 2026-11-25).

Maintains:
- /run/lynx/debug_tools.txt: Catalog of tools and default sample arguments
- /run/lynx/debug_cmd.txt: Command trigger interface from display UI
- /run/lynx/debug_raw.txt: Raw sensory and tool output stream (before Regex DB)
- /run/lynx/debug_translated.txt: Regex DB translated stream (after pattern matching)
"""

from __future__ import annotations

import argparse
import glob
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

AUTONOMY_DIRS = [
    Path(os.environ.get("NOOBIA", "/noobia")) / "common" / "autonomy",
    Path("/usr/local/lib/noobia/autonomy"),
    Path(os.environ.get("NOOBIA", "/noobia")) / "lynx" / "autonomy",
]
for d in AUTONOMY_DIRS:
    if d.exists() and str(d) not in sys.path:
        sys.path.insert(0, str(d))

try:
    import ranker
    from sense import parse_line
except ImportError:
    ranker = None
    parse_line = None

RUN_DIR = Path("/run/lynx")
STOP_FILE = Path(os.environ.get("LYNX_STOP_FILE", "/var/lib/lynx-agent/stop"))
TOOLS_DIR = Path("/usr/local/share/lynx/agent-tools")
PATTERNS_FILE = Path("/var/lib/noobia/autonomy/patterns.json")
FALLBACK_PATTERNS = Path(os.environ.get("NOOBIA", "/noobia")) / "lynx" / "autonomy" / "patterns-lynx.json"
MESSAGES_LOG = Path("/var/log/lynx/messages")

MAX_LINES = 100
SAMPLE_ARGS = {
    "lynx_speech": '{"text": "Hello Noobia"}',
    "lynx_media_play": '{"kind": "sound", "item": "chime"}',
    "lynx_media_stop": '{"kind": "sound"}',
    "lynx_camera_photo": '{}',
    "lynx_motion_read": '{"choice": "gyro"}',
    "lynx_net_diag": '{"action": "net-ifaces"}',
    "lynx_netintel": '{"action": "stats"}',
    "lynx_display_pose": '{"action": "status"}',
    "lynx_cellular_diag": '{"action": "sim-check"}',
    "lynx_haptic_pulse": '{"duration_ms": 50}',
    "lynx_haptic_stop": '{}',
    "lynx_flashlight_pulse": '{"duration_ms": 100}',
    "lynx_flashlight_stop": '{}',
    "lynx_codex": '{"prompt": "print(42)"}',
    "lynx_media_catalog": '{}',
    "lynx_battery_status": '{}',
    "lynx_thermal_status": '{}',
    "lynx_wifi_status": '{}',
    "lynx_platform_status": '{}',
    "lynx_security_status": '{}',
    "lynx_agent_health": '{}',
    "lynx_proximity_read": '{}',
    "lynx_light_read": '{}',
    "lynx_magnetometer_read": '{}',
    "lynx_touch_status": '{}',
    "lynx_touch_events": '{}',
    "lynx_sensorhub_status": '{}',
    "lynx_audio_status": '{}',
}


def load_patterns() -> list[dict]:
    path = PATTERNS_FILE if PATTERNS_FILE.exists() else FALLBACK_PATTERNS
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data.get("store") or data.get("patterns") or []
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def discover_tools() -> list[dict]:
    tools = []
    if not TOOLS_DIR.exists():
        return tools

    for p in sorted(TOOLS_DIR.glob("*.json")):
        name = p.stem
        sh_path = TOOLS_DIR / f"{name}.sh"
        if not sh_path.exists():
            continue
        desc = ""
        try:
            meta = json.loads(p.read_text(encoding="utf-8"))
            desc = meta.get("description", "").replace("\n", " ")
        except Exception:
            pass
        if len(desc) > 80:
            desc = desc[:77] + "..."
        sample = SAMPLE_ARGS.get(name, "{}")
        tools.append({"name": name, "sample": sample, "desc": desc, "script": str(sh_path)})
    return tools


def write_tools_catalog(tools: list[dict]) -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    out_file = RUN_DIR / "debug_tools.txt"
    lines = []
    for t in tools:
        lines.append(f"{t['name']}|{t['sample']}|{t['desc']}")
    out_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def translate_sense_line(raw: str, patterns: list[dict]) -> str:
    if not parse_line or not ranker:
        return raw

    try:
        parsed = parse_line(raw)
    except Exception:
        parsed = None

    if not parsed:
        # If not strict NOOBIA format, strip prefix and return
        return raw

    for pat in patterns:
        try:
            if ranker._pattern_matches(pat, parsed):
                msg = ranker.render_message(pat, parsed)
                pat_id = pat.get("id", "pattern")
                return f"[{pat_id}] {msg}"
        except Exception:
            continue

    sense = parsed.get("sense", "sense")
    event = parsed.get("event", "event")
    txt = parsed.get("text")
    if txt:
        return f"[{sense}.{event}] {txt}"
    fields = parsed.get("fields", {})
    fstr = " ".join(f"{k}={v}" for k, v in fields.items())
    return f"[{sense}.{event}] {fstr}" if fstr else f"[{sense}.{event}]"


def run_tool(name: str, args_json: str, tools_map: dict[str, dict]) -> tuple[str, str]:
    t = tools_map.get(name)
    if not t:
        err = f"[TOOL: {name}] error: unknown tool"
        return err, err

    script = t["script"]
    if not args_json.strip():
        args_json = "{}"

    t0 = time.time()
    cmd = [script] if os.access(script, os.X_OK) else ["/bin/sh", script]
    tool_timeout = 180 if name == "lynx_codex" else (60 if name == "lynx_camera_photo" else 30)
    try:
        proc = subprocess.run(
            cmd,
            input=args_json,
            capture_output=True,
            text=True,
            timeout=tool_timeout,
            check=False,
        )
        elapsed = time.time() - t0
        output = (proc.stdout + proc.stderr).strip()
        # Single-line or compact preview
        preview = " ".join(output.split())
        if len(preview) > 120:
            preview = preview[:117] + "..."

        raw_line = f"[TOOL: {name}] exit={proc.returncode} ({elapsed:.2f}s) -> {preview}"
        if proc.returncode == 0:
            trans_line = f"[TOOL: {name}] OK ({elapsed:.2f}s): {preview}"
        else:
            trans_line = f"[TOOL: {name}] FAIL (exit {proc.returncode}): {preview}"
        return raw_line, trans_line
    except subprocess.TimeoutExpired:
        msg = f"[TOOL: {name}] TIMEOUT after {tool_timeout}s"
        return msg, msg
    except Exception as exc:
        msg = f"[TOOL: {name}] ERROR: {exc}"
        return msg, msg


class DebugSession:
    def __init__(self):
        self.raw_lines: list[str] = []
        self.trans_lines: list[str] = []
        self.patterns = load_patterns()
        self.tools = discover_tools()
        self.tools_map = {t["name"]: t for t in self.tools}
        write_tools_catalog(self.tools)

    def add_line(self, raw: str, trans: str) -> None:
        ts = time.strftime("%H:%M:%S")
        self.raw_lines.append(f"{ts} {raw}")
        self.trans_lines.append(f"{ts} {trans}")
        if len(self.raw_lines) > MAX_LINES:
            self.raw_lines.pop(0)
        if len(self.trans_lines) > MAX_LINES:
            self.trans_lines.pop(0)
        self.flush()

    def clear(self) -> None:
        self.raw_lines.clear()
        self.trans_lines.clear()
        self.flush()

    def flush(self) -> None:
        RUN_DIR.mkdir(parents=True, exist_ok=True)
        (RUN_DIR / "debug_raw.txt.tmp").write_text("\n".join(self.raw_lines) + "\n", encoding="utf-8")
        (RUN_DIR / "debug_raw.txt.tmp").replace(RUN_DIR / "debug_raw.txt")

        (RUN_DIR / "debug_translated.txt.tmp").write_text("\n".join(self.trans_lines) + "\n", encoding="utf-8")
        (RUN_DIR / "debug_translated.txt.tmp").replace(RUN_DIR / "debug_translated.txt")

    def handle_command(self, cmd: str) -> None:
        cmd = cmd.strip()
        if not cmd:
            return
        if cmd == "CLEAR":
            self.clear()
            return
        if cmd in ("AI_ON", "AI_START"):
            try:
                STOP_FILE.unlink(missing_ok=True)
                subprocess.run(["/sbin/rc-service", "lynx-agent-worker", "start"], check=False, timeout=10)
                subprocess.run(["/sbin/rc-service", "noobia-autonomyd", "start"], check=False, timeout=10)
                self.add_line("[DEBUG] AI turned ON (worker & autonomyd started)",
                              "[DEBUG] AI turned ON (worker & autonomyd started)")
            except Exception as exc:
                self.add_line(f"[DEBUG] AI start error: {exc}", f"[DEBUG] AI start error: {exc}")
            return
        if cmd in ("AI_OFF", "AI_STOP"):
            try:
                STOP_FILE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                STOP_FILE.touch(mode=0o600, exist_ok=True)
                subprocess.run(["/sbin/rc-service", "lynx-agent-worker", "stop"], check=False, timeout=10)
                subprocess.run(["/sbin/rc-service", "noobia-autonomyd", "stop"], check=False, timeout=10)
                self.add_line("[DEBUG] AI turned OFF (worker & autonomyd stopped)",
                              "[DEBUG] AI turned OFF (worker & autonomyd stopped)")
            except Exception as exc:
                self.add_line(f"[DEBUG] AI stop error: {exc}", f"[DEBUG] AI stop error: {exc}")
            return
        if cmd == "AI_TOGGLE":
            if STOP_FILE.exists():
                self.handle_command("AI_ON")
            else:
                self.handle_command("AI_OFF")
            return
        if cmd.startswith("RUN "):
            parts = cmd[4:].split(None, 1)
            name = parts[0]
            args = parts[1] if len(parts) > 1 else "{}"
            raw, trans = run_tool(name, args, self.tools_map)
            self.add_line(raw, trans)


def run_daemon() -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    pid_file = RUN_DIR / "debug-helper.pid"
    pid_file.write_text(str(os.getpid()), encoding="utf-8")

    session = DebugSession()
    session.add_line("[DEBUG] Lynx Debug Mode initialized. AI stopped.", "[DEBUG] Lynx Debug Mode initialized. AI stopped.")

    # Tail syslog messages
    log_file = None
    if MESSAGES_LOG.exists():
        try:
            log_file = open(MESSAGES_LOG, "r", encoding="utf-8", errors="replace")
            # seek to end or last 2KB
            log_file.seek(0, os.SEEK_END)
            size = log_file.tell()
            log_file.seek(max(0, size - 4096), os.SEEK_SET)
            # read initial existing lines
            for line in log_file.readlines()[-15:]:
                if "noobia-sense" in line and "NOOBIA P" in line:
                    idx = line.find("NOOBIA P")
                    raw = line[idx:].strip()
                    trans = translate_sense_line(raw, session.patterns)
                    session.add_line(f"[SENSE] {raw}", f"[SENSE] {trans}")
                elif "harness chunk" in line or "chunk_closed" in line:
                    idx = line.find("harness chunk") if "harness chunk" in line else line.find("chunk_closed")
                    entry = line[idx:].strip()
                    session.add_line(f"[CHUNK] {entry}", f"[CHUNK] {entry}")
        except Exception:
            log_file = None

    cmd_file = RUN_DIR / "debug_cmd.txt"
    running = True

    def _sig_handler(sig, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, _sig_handler)
    signal.signal(signal.SIGINT, _sig_handler)

    while running:
        # Check command file
        if cmd_file.exists():
            try:
                cmd = cmd_file.read_text(encoding="utf-8").strip()
                cmd_file.unlink(missing_ok=True)
                if cmd:
                    session.handle_command(cmd)
            except Exception:
                pass

        # Check log lines
        if log_file:
            while True:
                line = log_file.readline()
                if not line:
                    break
                if "noobia-sense" in line and "NOOBIA P" in line:
                    idx = line.find("NOOBIA P")
                    raw = line[idx:].strip()
                    trans = translate_sense_line(raw, session.patterns)
                    session.add_line(f"[SENSE] {raw}", f"[SENSE] {trans}")
                elif "harness chunk" in line or "chunk_closed" in line:
                    idx = line.find("harness chunk") if "harness chunk" in line else line.find("chunk_closed")
                    entry = line[idx:].strip()
                    session.add_line(f"[CHUNK] {entry}", f"[CHUNK] {entry}")

        time.sleep(0.1)

    if log_file:
        log_file.close()
    pid_file.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Lynx Debug Mode Helper")
    parser.add_argument("--daemon", action="store_true", help="Run background tail & runner")
    parser.add_argument("--test-run", nargs="+", help="Test tool execution: <tool> [args_json]")
    parser.add_argument("--translate", type=str, help="Test translate one sense line")
    args = parser.parse_args()

    if args.translate:
        patterns = load_patterns()
        print(translate_sense_line(args.translate, patterns))
        return

    if args.test_run:
        name = args.test_run[0]
        args_json = args.test_run[1] if len(args.test_run) > 1 else "{}"
        tools = discover_tools()
        tools_map = {t["name"]: t for t in tools}
        raw, trans = run_tool(name, args_json, tools_map)
        print("RAW:", raw)
        print("TRANS:", trans)
        return

    if args.daemon:
        run_daemon()
    else:
        # Just write catalog and exit
        tools = discover_tools()
        write_tools_catalog(tools)
        print(f"Catalog updated: {len(tools)} tools written to {RUN_DIR / 'debug_tools.txt'}")


if __name__ == "__main__":
    main()
