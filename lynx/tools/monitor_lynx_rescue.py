#!/usr/bin/env python3
"""Monitor Lynx V19 rescue SSH continuity without changing the phone.

Usage: python3 monitor_lynx_rescue.py --start [--interval 20]
       python3 monitor_lynx_rescue.py --status
       python3 monitor_lynx_rescue.py --stop
Events and current status stay in /noobia/lynx/logs/rescue-continuity/.
"""

import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve()
OUT = ROOT / "logs/rescue-continuity"
PID_FILE = OUT / "monitor.pid"
STATUS_FILE = OUT / "status.json"
EVENTS_FILE = OUT / "events.jsonl"
RUNNER_LOG = OUT / "runner.log"
LOCK_FILE = OUT / "monitor.lock"
IP = "192.168.100.7"
KERNEL = "5.10.149-android12-9-o-g311738fbb5a8"
INIT_SHA = "68e5dd41e7f134b651308e2d510543483a1f5bc1a3a57908e4936128573088f2"
BOOT_ID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")
COMMAND = "cat /proc/sys/kernel/random/boot_id; uname -r; sha256sum /init | cut -c1-64; cat /proc/uptime"
stopping = False


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def active_pid():
    try:
        pid = int(PID_FILE.read_text().strip())
        command = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode()
        if str(HERE) in command and "--run" in command:
            return pid
    except (OSError, ValueError):
        pass
    return None


def probe():
    started = time.monotonic()
    try:
        process = subprocess.run(ssh_command(IP, COMMAND), capture_output=True,
                                 text=True, timeout=12)
    except subprocess.TimeoutExpired:
        return {"state": "offline", "error": "SSH timeout",
                "elapsed_seconds": round(time.monotonic() - started, 3)}
    elapsed = round(time.monotonic() - started, 3)
    if process.returncode:
        return {"state": "offline", "error": process.stderr.strip()[-240:],
                "exit_code": process.returncode, "elapsed_seconds": elapsed}
    lines = process.stdout.splitlines()
    if len(lines) != 4 or not BOOT_ID.fullmatch(lines[0]) or \
            lines[1] != KERNEL or lines[2] != INIT_SHA:
        return {"state": "identity_mismatch", "error": "V19 identity response differed",
                "elapsed_seconds": elapsed}
    try:
        uptime = float(lines[3].split()[0])
    except (IndexError, ValueError):
        return {"state": "identity_mismatch", "error": "uptime was invalid",
                "elapsed_seconds": elapsed}
    return {"state": "online_v19", "boot_id": lines[0],
            "uptime_seconds": round(uptime, 2), "elapsed_seconds": elapsed}


def request_stop(_signum, _frame):
    global stopping
    stopping = True


def run(interval):
    global stopping
    os.umask(0o077)
    OUT.mkdir(parents=True, exist_ok=True, mode=0o700)
    with LOCK_FILE.open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("Lynx rescue monitor already running")
        PID_FILE.write_text(str(os.getpid()) + "\n")
        signal.signal(signal.SIGTERM, request_stop)
        signal.signal(signal.SIGINT, request_stop)
        status = {"state": "starting", "pid": os.getpid(), "ip": IP,
                  "interval_seconds": interval, "started_at": now(),
                  "samples": 0, "successes": 0, "failures": 0,
                  "consecutive_failures": 0, "boot_changes": 0,
                  "last_online_at": None, "current_boot_id": None,
                  "note": "Sampled SSH continuity; gaps between samples are not observed."}
        atomic_json(STATUS_FILE, status)
        with EVENTS_FILE.open("a", buffering=1) as events:
            while not stopping:
                result = probe()
                result["checked_at"] = now()
                result["sample"] = status["samples"] + 1
                status["samples"] += 1
                if result["state"] == "online_v19":
                    status["successes"] += 1
                    status["consecutive_failures"] = 0
                    status["last_online_at"] = result["checked_at"]
                    old_boot = status["current_boot_id"]
                    if old_boot and old_boot != result["boot_id"]:
                        status["boot_changes"] += 1
                        result["boot_changed_from"] = old_boot
                    status["current_boot_id"] = result["boot_id"]
                else:
                    status["failures"] += 1
                    status["consecutive_failures"] += 1
                status["state"] = result["state"]
                status["last_checked_at"] = result["checked_at"]
                status["last_error"] = result.get("error")
                events.write(json.dumps(result) + "\n")
                atomic_json(STATUS_FILE, status)
                end = time.monotonic() + interval
                while not stopping and time.monotonic() < end:
                    time.sleep(min(1, end - time.monotonic()))
        status["state"] = "stopped"
        status["stopped_at"] = now()
        atomic_json(STATUS_FILE, status)
        PID_FILE.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--start", action="store_true")
    mode.add_argument("--run", action="store_true", help=argparse.SUPPRESS)
    mode.add_argument("--status", action="store_true")
    mode.add_argument("--stop", action="store_true")
    parser.add_argument("--interval", type=int, default=20)
    args = parser.parse_args()
    if not 10 <= args.interval <= 300:
        parser.error("--interval must be 10 to 300 seconds")
    if args.run:
        run(args.interval)
        return
    if args.status:
        data = json.loads(STATUS_FILE.read_text()) if STATUS_FILE.exists() else {"state": "not_started"}
        data["process_running"] = active_pid() is not None
        print(json.dumps(data, indent=2))
        return
    if args.stop:
        pid = active_pid()
        if pid is None:
            print("Lynx rescue monitor is not running")
            return
        os.kill(pid, signal.SIGTERM)
        print(f"Stop requested for Lynx rescue monitor PID {pid}")
        return
    if active_pid() is not None:
        print("Lynx rescue monitor is already running")
        return
    os.umask(0o077)
    OUT.mkdir(parents=True, exist_ok=True, mode=0o700)
    with RUNNER_LOG.open("a") as log:
        subprocess.Popen([sys.executable, str(HERE), "--run", "--interval", str(args.interval)],
                         stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                         cwd=ROOT, start_new_session=True, close_fds=True)
    for _ in range(30):
        pid = active_pid()
        if pid is not None and STATUS_FILE.exists() and \
                json.loads(STATUS_FILE.read_text()).get("pid") == pid:
            print(json.dumps({"state": "started", "status": str(STATUS_FILE),
                              "events": str(EVENTS_FILE), "interval_seconds": args.interval}))
            return
        time.sleep(0.1)
    raise SystemExit("Monitor failed to start; inspect runner.log")


if __name__ == "__main__":
    main()
