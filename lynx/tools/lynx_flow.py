#!/usr/bin/env python3
"""lynx-flow: End-to-end diagnostic flow for Lynx's sensory-cognitive-effector path.

Traces and displays the entire stream:
  1. Hardware & Power: battery capacity, charge current, temperature, guard switches.
  2. Senses & Daemons: OpenRC service health, raw touch/sense emissions in syslog.
  3. Autonomy & Queue: Aigel chunking, job queue (pending, running, done).
  4. Thought & Display Sync: user inputs, Lynx's thoughts, front screen vs chat screen match.

Can run directly on Lynx (local inspection) or on Nexus (via lynx-remote SSH bridge).
"""

from __future__ import annotations

import argparse
import glob
import json
import os
from pathlib import Path
import subprocess
import sys
import time

CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def is_on_lynx() -> bool:
    """Return True if running locally on the Lynx phone."""
    return Path("/var/log/lynx").exists() or Path("/etc/alpine-release").exists()


def run_cmd(cmd: str) -> str:
    """Run a shell command locally and return stdout."""
    try:
        res = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=10
        )
        return res.stdout.strip()
    except Exception as e:
        return f"ERROR: {e}"


def get_service_status(service: str) -> tuple[str, bool]:
    """Check OpenRC service status."""
    res = run_cmd(f"rc-service {service} status")
    if "status: started" in res:
        return "started", True
    if "status: stopped" in res:
        return "stopped", False
    return res or "unknown", False


def read_battery_info() -> dict:
    """Read battery and thermal telemetry."""
    info = {
        "capacity": "?",
        "current_mA": "?",
        "temp_C": "?",
        "voltage_mV": "?",
        "power_guard": "unknown",
        "thermal_guard": "unknown",
    }
    # Check /run/lynx/battery-last first
    blast = Path("/run/lynx/battery-last")
    if blast.exists():
        try:
            bdict = {}
            for line in blast.read_text().splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    bdict[k.strip()] = v.strip()
            if "capacity_percent" in bdict:
                info["capacity"] = f"{bdict['capacity_percent']}%"
            if "gauge_current_ma_signed" in bdict:
                info["current_mA"] = f"{bdict['gauge_current_ma_signed']} mA"
            if "temperature_millidegrees_celsius" in bdict:
                t_mc = int(bdict["temperature_millidegrees_celsius"])
                info["temp_C"] = f"{t_mc / 1000.0:.1f} °C"
            if "pack_voltage_mv" in bdict:
                info["voltage_mV"] = f"{bdict['pack_voltage_mv']} mV"
        except Exception:
            pass

    cap_p = Path("/sys/class/power_supply/battery/capacity")
    if cap_p.exists():
        try:
            info["capacity"] = cap_p.read_text().strip() + "%"
        except Exception:
            pass

    cur_p = Path("/sys/class/power_supply/battery/current_now")
    if cur_p.exists():
        try:
            val = int(cur_p.read_text().strip())
            # microamps to milliamps
            info["current_mA"] = f"{val // 1000} mA"
        except Exception:
            pass

    temp_p = Path("/sys/class/power_supply/battery/temp")
    if temp_p.exists():
        try:
            t = int(temp_p.read_text().strip())
            info["temp_C"] = f"{t / 10.0:.1f} °C"
        except Exception:
            pass

    volt_p = Path("/sys/class/power_supply/battery/voltage_now")
    if volt_p.exists():
        try:
            v = int(volt_p.read_text().strip())
            info["voltage_mV"] = f"{v // 1000} mV"
        except Exception:
            pass

    sw_p = Path("/etc/noobia/lynx_switch.json")
    if sw_p.exists():
        try:
            sw = json.loads(sw_p.read_text())
            info["power_guard"] = (
                "ENABLED" if sw.get("power_guard_enabled", True) else "DISABLED (GUARD OFF)"
            )
            info["thermal_guard"] = (
                "ENABLED" if sw.get("thermal_guard_enabled", True) else "DISABLED (GUARD OFF)"
            )
        except Exception:
            pass
    return info


def get_senses_and_touch() -> dict:
    """Inspect syslog for recent senses and touch queue."""
    res = {
        "recent_senses": [],
        "last_touch_line": "None",
        "touch_queue_state": "unknown",
    }
    msg_path = Path("/var/log/lynx/messages")
    if msg_path.exists():
        try:
            # Read last 60 lines looking for NOOBIA
            lines = run_cmd("grep 'NOOBIA' /var/log/lynx/messages | tail -n 15").splitlines()
            res["recent_senses"] = [l.strip() for l in lines if l.strip()]
            for l in reversed(lines):
                if "touch" in l:
                    res["last_touch_line"] = l.strip()
                    break
        except Exception as e:
            res["recent_senses"] = [f"Error reading syslog: {e}"]

    # Touch queue status
    t_status = Path("/var/run/lynx-touch.status")
    if t_status.exists():
        try:
            res["touch_queue_state"] = t_status.read_text().strip()
        except Exception:
            pass
    return res


def get_job_queue() -> dict:
    """Inspect Lynx agent job queue."""
    jobs_dir = Path("/var/lib/lynx-agent/jobs")
    res = {
        "pending": [],
        "running": [],
        "done": 0,
        "last_done": "None",
    }
    if jobs_dir.exists():
        try:
            res["pending"] = [p.stem for p in jobs_dir.glob("*.pending")]
            running_files = list(jobs_dir.glob("*.running"))
            for rf in running_files:
                snippet = "no details"
                try:
                    data = json.loads(rf.read_text())
                    prompt = data.get("prompt", "")
                    obs_idx = prompt.find("Observation (data):")
                    if obs_idx != -1:
                        snippet = prompt[obs_idx : obs_idx + 150].replace("\n", " ") + "..."
                    else:
                        snippet = prompt[:120].replace("\n", " ") + "..."
                except Exception:
                    pass
                res["running"].append({"id": rf.stem, "snippet": snippet})

            done_files = sorted(
                jobs_dir.glob("*.done"),
                key=lambda p: p.stat().st_mtime if p.exists() else 0,
                reverse=True,
            )
            res["done"] = len(done_files)
            if done_files:
                last_f = done_files[0]
                try:
                    data = json.loads(last_f.read_text())
                    txt = data.get("text", "").strip().replace("\n", " ")
                    res["last_done"] = f"[{last_f.stem[:8]}] {txt[:120]}"
                except Exception:
                    res["last_done"] = f"[{last_f.stem[:8]}] (could not parse)"
        except Exception as e:
            res["error"] = str(e)
    return res


def get_thought_and_display_sync() -> dict:
    """Analyze thoughts file, front screen thought, and chat screen match."""
    thought_path = Path("/var/lib/noobia/lynx_thought.txt")
    res = {
        "total_lines": 0,
        "last_user_input": "None",
        "last_lynx_thought": "None",
        "front_screen_thought": "None",
        "chat_screen_latest": [],
        "matches": False,
    }
    if not thought_path.exists():
        return res

    try:
        lines = [l.strip() for l in thought_path.read_text(errors="replace").splitlines() if l.strip()]
        res["total_lines"] = len(lines)
        if not lines:
            return res

        for l in reversed(lines):
            if (l.startswith("Noob:") or l.startswith("User:")) and res["last_user_input"] == "None":
                res["last_user_input"] = l
            elif not l.startswith("Noob:") and not l.startswith("User:") and res["last_lynx_thought"] == "None":
                res["last_lynx_thought"] = l

        # In our updated paint_thoughts, front screen isolates the last line that isn't Noob: or User:
        res["front_screen_thought"] = res["last_lynx_thought"]

        # Chat screen shows the last 6 lines (both user and lynx)
        res["chat_screen_latest"] = lines[-6:]

        # Check if front screen matches the latest Lynx thought found in chat
        if res["front_screen_thought"] != "None" and res["front_screen_thought"] == res["last_lynx_thought"]:
            res["matches"] = True
    except Exception as e:
        res["error"] = str(e)

    return res


def print_local_flow():
    """Print the formatted flow report."""
    batt = read_battery_info()
    senses = get_senses_and_touch()
    queue = get_job_queue()
    thoughts = get_thought_and_display_sync()

    print(f"\n{BOLD}{CYAN}======================================================================{RESET}")
    print(f"{BOLD}{CYAN}             LYNX SENSORY-COGNITIVE-EFFECTOR FLOW MONITOR             {RESET}")
    print(f"{BOLD}{CYAN}======================================================================{RESET}")

    # 1. HARDWARE & POWER
    print(f"\n{BOLD}1. HARDWARE & POWER FLOW{RESET}")
    print(f"  Battery:        {batt['capacity']}  |  Current: {batt['current_mA']}  |  Temp: {batt['temp_C']}  |  Volt: {batt['voltage_mV']}")
    p_col = YELLOW if "DISABLED" in batt['power_guard'] else GREEN
    t_col = YELLOW if "DISABLED" in batt['thermal_guard'] else GREEN
    print(f"  Guards:         Power Guard: {p_col}{batt['power_guard']}{RESET}  |  Thermal Guard: {t_col}{batt['thermal_guard']}{RESET}")

    # 2. SENSES & OPENRC SERVICES
    print(f"\n{BOLD}2. SENSES & DAEMON SERVICES FLOW{RESET}")
    services = ["lynx-senses", "noobia-autonomyd", "lynx-agent-worker", "lynx-display", "lynx-speech"]
    svc_status_strs = []
    all_svcs_up = True
    for s in services:
        st, ok = get_service_status(s)
        if not ok:
            all_svcs_up = False
        color = GREEN if ok else RED
        svc_status_strs.append(f"{s}: {color}{st}{RESET}")
    print("  Services:       " + "  ".join(svc_status_strs))

    print(f"  Last Touch:     {senses['last_touch_line']}")
    if senses["recent_senses"]:
        print(f"  Recent Senses ({len(senses['recent_senses'])}):")
        for s in senses["recent_senses"][-5:]:
            print(f"    {DIM}• {s}{RESET}")
    else:
        print(f"  Recent Senses:  {YELLOW}(No recent senses in syslog){RESET}")

    # 3. AUTONOMY & JOB QUEUE
    print(f"\n{BOLD}3. AUTONOMY & JOB QUEUE FLOW (AIGEL -> LYNX AGENT){RESET}")
    p_count = len(queue["pending"])
    r_count = len(queue["running"])
    d_count = queue["done"]
    q_col = GREEN if r_count == 0 else YELLOW
    print(f"  Queue State:    {q_col}{p_count} PENDING | {r_count} RUNNING | {d_count} COMPLETED{RESET}")
    if queue["running"]:
        for rj in queue["running"]:
            print(f"    {YELLOW}▶ RUNNING [{rj['id'][:8]}]: {rj['snippet']}{RESET}")
    print(f"  Last Response:  {queue['last_done']}")

    # 4. CONSCIOUS THOUGHT & DISPLAY SYNC
    print(f"\n{BOLD}4. CONSCIOUS THOUGHT & DISPLAY SYNC FLOW{RESET}")
    print(f"  Total Thoughts: {thoughts['total_lines']} entries in /var/lib/noobia/lynx_thought.txt")
    print(f"  Last User Word: {CYAN}{thoughts['last_user_input']}{RESET}")
    print(f"  Latest Thought: {BOLD}{thoughts['last_lynx_thought']}{RESET}")
    print(f"  Front Screen:   {GREEN if thoughts['matches'] else RED}{thoughts['front_screen_thought']}{RESET}")
    
    sync_badge = f"{GREEN}[MATCH - IN SYNC]{RESET}" if thoughts["matches"] else f"{RED}[MISMATCH - OUTDATED]{RESET}"
    print(f"  Sync Status:    {sync_badge}")

    print(f"\n  Chat Stream Tail:")
    for ct in thoughts["chat_screen_latest"]:
        if ct.startswith("Noob:") or ct.startswith("User:"):
            print(f"    {CYAN}▸ {ct}{RESET}")
        else:
            print(f"    {WHITE if 'WHITE' in globals() else ''}▸ {ct}{RESET}")

    print(f"\n{BOLD}{CYAN}======================================================================{RESET}\n")


def forward_to_lynx():
    """Run lynx-flow remotely on Lynx via python lynx_remote.py."""
    repo_root = Path(os.environ.get("NOOBIA", "/noobia"))
    remote_helper = repo_root / "lynx/tools/lynx_remote.py"
    if not remote_helper.exists():
        print(f"{RED}Cannot find {remote_helper} to reach Lynx.{RESET}", file=sys.stderr)
        sys.exit(1)

    cmd = ["python3", str(remote_helper), "run", "/usr/local/bin/lynx-flow", "--timeout", "15"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.stdout:
        print(res.stdout)
    if res.returncode != 0 and res.stderr:
        print(f"{RED}Remote execution error: {res.stderr}{RESET}", file=sys.stderr)
    sys.exit(res.returncode)


def main():
    parser = argparse.ArgumentParser(description="Lynx Sensory-Cognitive-Effector Flow Monitor")
    parser.parse_args()

    if is_on_lynx():
        print_local_flow()
    else:
        forward_to_lynx()


if __name__ == "__main__":
    main()
