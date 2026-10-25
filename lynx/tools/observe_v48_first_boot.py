#!/usr/bin/env python3
"""Read-only, pinned SSH observer for the first V48 boot."""

import json
import os
from pathlib import Path
import socket
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
IPS = ("192.168.100.8", "192.168.100.7")
INIT_SHA = "b560f233f5ecf838b5e948d0cd3685b676a84f3097adb00d2c8bfa6e5446ab1f"
KERNEL = "5.10.149-android12-9-o-g311738fbb5a8"
COMMAND_COMMON = (
    "set -eu; printf 'BOOT_ID='; cat /proc/sys/kernel/random/boot_id; "
    "printf 'KERNEL='; uname -r; "
    "printf 'UPTIME='; cat /proc/uptime; "
    "printf 'BATTERY_BEGIN\\n'; cat /sys/bus/i2c/devices/7-0055/battery_snapshot 2>&1 || true; "
    "printf 'BATTERY_END\\n'; "
    "for p in /sys/class/power_supply/*; do "
    "printf 'SUPPLY=%s\\n' \"$p\"; "
    "for x in online status; do "
    "[ ! -r \"$p/$x\" ] || { printf '%s=' \"$x\"; cat \"$p/$x\"; }; "
    "done; done; "
    "printf 'CPU_TEMP='; cat /sys/class/thermal/thermal_zone0/temp 2>&1 || true; "
    "printf 'ALPINE='; cat /etc/alpine-release 2>/dev/null || true; "
    "printf 'HEALTH='; /sbin/rc-service lynx-health status 2>&1 || true; "
    "printf 'RESERVE='; /sbin/rc-service lynx-battery-reserve status 2>&1 || true"
)


def connected(ip, port):
    with socket.socket() as connection:
        connection.settimeout(1)
        return connection.connect_ex((ip, port)) == 0


def ssh(ip, port):
    identity = ("printf 'INIT_SHA='; sha256sum /init | cut -c1-64; "
                if port == 22 else "")
    command = ssh_command(ip, "set -eu; " + identity + COMMAND_COMMON)
    command[-2:-2] = ["-p", str(port)]
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=15)
        return {"exit_code": done.returncode, "stdout": done.stdout,
                "stderr": done.stderr[-500:]}
    except subprocess.TimeoutExpired:
        return {"error": "SSH timed out"}


def main():
    os.umask(0o077)
    out = ROOT / "logs" / f"v48-first-boot-{time.time_ns()}"
    out.mkdir(mode=0o700)
    events = out / "events.jsonl"
    deadline = time.monotonic() + 600
    last_ports = None
    samples = 0
    print(json.dumps({"state": "listening", "events": str(events)}), flush=True)
    while time.monotonic() < deadline:
        endpoints = [(ip, port) for ip in IPS for port in (22, 2222)
                     if connected(ip, port)]
        if endpoints != last_ports:
            with events.open("a") as stream:
                stream.write(json.dumps({"time_ns": time.time_ns(), "endpoints": endpoints}) + "\n")
            print(json.dumps({"endpoints": endpoints}), flush=True)
            last_ports = endpoints
        if endpoints:
            ip, port = sorted(endpoints, key=lambda entry: entry[1] == 2222,
                              reverse=True)[0]
            result = ssh(ip, port)
            result.update(time_ns=time.time_ns(), ip=ip, port=port)
            with events.open("a") as stream:
                stream.write(json.dumps(result) + "\n")
            if result.get("exit_code") == 0:
                lines = result["stdout"].splitlines()
                good = (f"KERNEL={KERNEL}" in lines and
                        (f"INIT_SHA={INIT_SHA}" in lines if port == 22
                         else "ALPINE=3.24.2" in lines))
                print(json.dumps({"ssh": "read", "ip": ip, "port": port,
                                  "v48_identity": good, "events": str(events)}), flush=True)
                if good and port == 2222:
                    samples += 1
                    if samples >= 3:
                        print(json.dumps({"state": "v48-alpine-observed-3-times",
                                          "events": str(events)}), flush=True)
                        return
            time.sleep(20)
        else:
            time.sleep(3)
    print(json.dumps({"state": "timeout", "events": str(events)}), flush=True)


if __name__ == "__main__":
    main()
