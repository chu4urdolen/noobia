#!/usr/bin/env python3
"""Sample Lynx rescue charger ADC for one hour; never write to the phone.

Usage: python3 observe_lynx_charge_hour.py --start
       python3 observe_lynx_charge_hour.py --status
Results: /noobia/lynx/logs/rescue-charge-hour/
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve()
OUT = ROOT / "logs/rescue-charge-hour"
STATUS = OUT / "status.json"
SAMPLES = OUT / "samples.jsonl"
RUNNER = OUT / "runner.log"
IP = "192.168.100.7"
FIELDS = ("in_current5_raw", "in_current5_scale", "in_current6_raw",
          "in_current6_scale", "in_voltage1_raw", "in_voltage1_scale",
          "in_voltage4_raw", "in_voltage4_scale")
COMMAND = (
    "set -eu; cat /proc/sys/kernel/random/boot_id; "
    "d=/sys/bus/iio/devices/iio:device0; "
    "for x in " + " ".join(FIELDS) + "; do "
    "printf '%s=' \"$x\"; cat \"$d/$x\"; done; "
    "p=/sys/class/power_supply/11e01000.i2c:mt6375@34:chg; "
    "printf 'online='; cat \"$p/online\"; "
    "printf 'status='; cat \"$p/status\""
)


def utc():
    return datetime.now(timezone.utc).isoformat()


def save_status(data):
    temp = STATUS.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2) + "\n")
    temp.replace(STATUS)


def probe():
    record = {"at": utc()}
    try:
        done = subprocess.run(ssh_command(IP, COMMAND), capture_output=True,
                              text=True, timeout=15)
        record["ssh_exit"] = done.returncode
        if done.returncode:
            record["error"] = done.stderr.strip()[-250:]
            return record
        lines = done.stdout.splitlines()
        if len(lines) != len(FIELDS) + 3:
            record["error"] = "unexpected ADC response length"
            return record
        record["boot_id"] = lines[0]
        values = dict(line.split("=", 1) for line in lines[1:] if "=" in line)
        if set(values) != set(FIELDS) | {"online", "status"}:
            record["error"] = "unexpected ADC fields"
            return record
        for field in FIELDS:
            values[field] = int(values[field])
        record["values"] = values
    except (subprocess.TimeoutExpired, ValueError) as exc:
        record["error"] = type(exc).__name__
    return record


def run():
    os.umask(0o077)
    OUT.mkdir(parents=True, exist_ok=True, mode=0o700)
    started = time.monotonic()
    report = {"state": "running", "started_at": utc(), "pid": os.getpid(),
              "duration_seconds": 3600, "interval_seconds": 300,
              "samples": 0, "successful_samples": 0, "failed_samples": 0,
              "phone_writes": False, "limit": "ADC and voltage trend are not a USB power meter or direct state-of-charge proof."}
    save_status(report)
    with SAMPLES.open("a", buffering=1) as output:
        while time.monotonic() - started < 3600:
            row = probe()
            output.write(json.dumps(row) + "\n")
            report["samples"] += 1
            report["successful_samples" if "values" in row else "failed_samples"] += 1
            report["last_sample_at"] = row["at"]
            report["last_sample"] = row
            save_status(report)
            next_time = started + report["samples"] * 300
            time.sleep(max(0, min(next_time - time.monotonic(), 3600 - (time.monotonic() - started))))
    rows = [json.loads(line) for line in SAMPLES.read_text().splitlines()]
    good = [row for row in rows if "values" in row]
    if good:
        report["first_vbat_raw"] = good[0]["values"]["in_voltage4_raw"]
        report["last_vbat_raw"] = good[-1]["values"]["in_voltage4_raw"]
        report["vbat_raw_delta"] = report["last_vbat_raw"] - report["first_vbat_raw"]
        report["ibus_nonzero_samples"] = sum(
            row["values"]["in_current5_raw"] != 0 for row in good)
        report["boot_ids"] = sorted({row["boot_id"] for row in good})
    report["state"] = "complete"
    report["finished_at"] = utc()
    save_status(report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--start", action="store_true")
    mode.add_argument("--run", action="store_true", help=argparse.SUPPRESS)
    mode.add_argument("--status", action="store_true")
    args = parser.parse_args()
    if args.run:
        run()
    elif args.status:
        print(STATUS.read_text() if STATUS.exists() else json.dumps({"state": "not_started"}))
    else:
        if STATUS.exists() and json.loads(STATUS.read_text()).get("state") == "running":
            print("Charge trend capture is already running")
            return
        os.umask(0o077)
        OUT.mkdir(parents=True, exist_ok=True, mode=0o700)
        with RUNNER.open("a") as log:
            subprocess.Popen([sys.executable, str(HERE), "--run"],
                             stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                             cwd=ROOT, start_new_session=True, close_fds=True)
        for _ in range(30):
            if STATUS.exists() and json.loads(STATUS.read_text()).get("state") == "running":
                print(json.dumps({"state": "started", "status": str(STATUS),
                                  "samples": str(SAMPLES)}))
                return
            time.sleep(0.1)
        raise SystemExit("Charge trend capture failed to start; inspect runner.log")


if __name__ == "__main__":
    main()
