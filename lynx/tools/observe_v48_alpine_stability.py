#!/usr/bin/env python3
"""Bounded read-only stability watch for Lynx V48 Alpine over pinned SSH."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
SERVICES = ("lynx-health", "lynx-battery-reserve", "lynx-local-logs",
            "lynx-wifi", "lynx-dropbear", "lynx-maintenance")
COMMAND = """set -u
printf 'BOOT_ID='; cat /proc/sys/kernel/random/boot_id
printf 'PID1='; readlink /proc/1/exe
printf 'ROOT_FS='; awk '$2=="/" {print $3; exit}' /proc/mounts
printf 'ALPINE='; cat /etc/alpine-release
printf 'UPTIME='; cat /proc/uptime
printf 'BATTERY_BEGIN\n'; cat /sys/bus/i2c/devices/7-0055/battery_snapshot
printf 'BATTERY_END\n'
for s in lynx-health lynx-battery-reserve lynx-local-logs lynx-wifi lynx-dropbear lynx-maintenance; do
 /sbin/rc-service "$s" status >/dev/null 2>&1
 printf 'SERVICE_%s=%s\n' "$s" "$?"
done
for p in /sys/class/power_supply/*; do
 [ -d "$p" ] || continue
 printf 'SUPPLY='; printf '%s\n' "$p"
 for f in online status; do
  [ ! -r "$p/$f" ] || { printf '%s=' "$f"; cat "$p/$f"; }
 done
done
printf 'CPU_TEMP='; cat /sys/class/thermal/thermal_zone0/temp
"""


def parse(output):
    values = {}
    for line in output.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boot-id", required=True)
    parser.add_argument("--ip", default="192.168.100.7")
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument("--interval", type=int, default=60)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", args.boot_id):
        parser.error("invalid boot ID")
    if not 2 <= args.samples <= 20 or not 10 <= args.interval <= 300:
        parser.error("samples or interval out of bounds")
    os.umask(0o077)
    out = ROOT / "logs" / f"v48-stability-{time.time_ns()}"
    out.mkdir(mode=0o700)
    records = out / "samples.jsonl"
    report = {"state": "running", "boot_id": args.boot_id, "ip": args.ip,
              "samples_requested": args.samples, "interval_seconds": args.interval,
              "samples_completed": 0, "healthy_samples": 0,
              "phone_writes": False, "started_at": datetime.now(timezone.utc).isoformat()}

    def save():
        temp = out / "result.tmp"
        temp.write_text(json.dumps(report, indent=2) + "\n")
        temp.replace(out / "result.json")

    save()
    with records.open("a", buffering=1) as log:
        for index in range(args.samples):
            sample = {"at": datetime.now(timezone.utc).isoformat(), "index": index + 1}
            command = ssh_command(args.ip, COMMAND)
            command[-2:-2] = ["-p", "2222"]
            try:
                done = subprocess.run(command, capture_output=True, text=True, timeout=20)
                sample["ssh_exit"] = done.returncode
                sample["data"] = parse(done.stdout)
                sample["stderr"] = done.stderr[-300:]
                fields = sample["data"]
                healthy = (done.returncode == 0 and fields.get("BOOT_ID") == args.boot_id and
                           fields.get("PID1") == "/sbin/openrc-init" and
                           fields.get("ROOT_FS") == "ext4" and
                           fields.get("ALPINE") == "3.24.2" and
                           all(fields.get(f"SERVICE_{service}") == "0"
                               for service in SERVICES) and
                           fields.get("capacity_error") == "0" and
                           fields.get("temperature_error") == "0")
                sample["healthy"] = healthy
            except subprocess.TimeoutExpired:
                sample.update(healthy=False, error="SSH timeout")
            log.write(json.dumps(sample) + "\n")
            report["samples_completed"] += 1
            report["healthy_samples"] += int(sample["healthy"])
            report["last_sample"] = sample
            save()
            fields = sample.get("data", {})
            print(json.dumps({"sample": index + 1, "healthy": sample["healthy"],
                              "capacity_percent": fields.get("capacity_percent"),
                              "battery_temp_mC": fields.get("temperature_millidegrees_celsius"),
                              "current_mA_signed": fields.get("gauge_current_ma_signed"),
                              "result": str(out / "result.json")}), flush=True)
            if index + 1 < args.samples:
                time.sleep(args.interval)
    report["state"] = "complete"
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    save()
    print(json.dumps({"state": report["state"], "healthy_samples": report["healthy_samples"],
                      "samples": report["samples_completed"], "result": str(out / "result.json")}),
          flush=True)


if __name__ == "__main__":
    main()
