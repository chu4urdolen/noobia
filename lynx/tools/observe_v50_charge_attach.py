#!/usr/bin/env python3
"""Record a bounded read-only charger/TCPC trend across a cable change."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
IP = "192.168.100.107"
COMMAND = (
    "cat /proc/sys/kernel/random/boot_id; "
    "cat /sys/bus/i2c/devices/7-0055/battery_snapshot; "
    "p=/sys/class/power_supply/11e01000.i2c:mt6375@34:chg; "
    "printf 'charger_online='; cat \"$p/online\"; "
    "printf 'charger_status='; cat \"$p/status\"; "
    "printf 'tcpc_pe_ready='; cat /sys/class/tcpc/type_c_port0/pe_ready"
)


def probe():
    argv = ssh_command(IP, COMMAND)
    argv[-2:-2] = ["-p", "2222"]
    record = {"time_ns": time.time_ns()}
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=6)
        record["ssh_exit"] = result.returncode
        if result.returncode:
            record["error"] = result.stderr[-220:]
            return record
        lines = result.stdout.splitlines()
        record["boot_id"] = lines[0]
        record["values"] = dict(line.split("=", 1) for line in lines[1:] if "=" in line)
    except subprocess.TimeoutExpired:
        record["error"] = "ssh-timeout"
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=180)
    args = parser.parse_args()
    if not 30 <= args.seconds <= 300:
        parser.error("--seconds must be 30..300")
    os.umask(0o077)
    out = ROOT / "logs" / f"v50-charge-attach-{time.time_ns()}"
    out.mkdir(mode=0o700)
    samples = out / "samples.jsonl"
    report = {"state": "running", "seconds": args.seconds,
              "phone_writes": False, "samples": str(samples)}
    print(json.dumps({"state": "listening", "samples": str(samples)}), flush=True)
    started = time.monotonic()
    last = None
    with samples.open("w", buffering=1) as stream:
        while time.monotonic() - started < args.seconds:
            row = probe()
            stream.write(json.dumps(row) + "\n")
            values = row.get("values", {})
            summary = {key: values.get(key) for key in
                       ("capacity_percent", "gauge_current_ma_signed",
                        "charger_online", "charger_status", "tcpc_pe_ready")}
            if "error" in row:
                summary["error"] = row["error"]
            if summary != last:
                print(json.dumps(summary), flush=True)
                last = summary
            time.sleep(5)
    report.update(state="complete", finished_ns=time.time_ns())
    (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": "complete", "result": str(out / 'result.json')}), flush=True)


if __name__ == "__main__":
    main()
