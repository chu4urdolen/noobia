#!/usr/bin/env python3
"""Observe V49/V50 recovery, Alpine, and early IOMMU state without writes."""

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
IPS = {"v49": ("192.168.100.7", "192.168.100.8", "192.168.100.9"),
       "v50": ("192.168.100.107",)}
INIT_SHA = "b560f233f5ecf838b5e948d0cd3685b676a84f3097adb00d2c8bfa6e5446ab1f"
KERNEL = "5.10.149-android12-9-o-g311738fbb5a8"


def connected(ip, port):
    with socket.socket() as sock:
        sock.settimeout(1)
        return sock.connect_ex((ip, port)) == 0


def ssh(ip, port):
    if port == 22:
        command = ("set -eu; printf 'BOOT_ID='; cat /proc/sys/kernel/random/boot_id; "
                   "printf 'KERNEL='; uname -r; "
                   "printf 'INIT_SHA='; sha256sum /init | cut -c1-64; "
                   "printf 'IOMMU_MODULE='; grep '^mtk_iommu ' /proc/modules || :; "
                   "printf 'CMDQ_MODULE='; grep '^mtk_cmdq_drv_ext ' /proc/modules || :; "
                   "printf 'GCE_DRIVER='; readlink /sys/bus/platform/devices/1e980000.gce/driver || :; "
                   "printf 'GCE_GROUP='; readlink /sys/bus/platform/devices/1e980000.gce/iommu_group || :; "
                   "printf 'IOMMU_BOOT_LOG='; grep 'CHECKPOINT_MODULE_OK mtk_iommu.ko' "
                   "/run/lynx/boot.log || :")
    else:
        command = ("set -eu; printf 'BOOT_ID='; cat /proc/sys/kernel/random/boot_id; "
                   "printf 'KERNEL='; uname -r; "
                   "printf 'ALPINE='; cat /etc/alpine-release; "
                   "printf 'IOMMU_MODULE='; grep '^mtk_iommu ' /proc/modules || :; "
                   "printf 'GCE_GROUP='; readlink /sys/bus/platform/devices/1e980000.gce/iommu_group || :; "
                   "/usr/local/bin/lynx-status --assert-ready")
    argv = ssh_command(ip, command)
    argv[-2:-2] = ["-p", str(port)]
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=15)
        return {"exit_code": done.returncode, "stdout": done.stdout,
                "stderr": done.stderr[-500:]}
    except subprocess.TimeoutExpired:
        return {"error": "SSH timed out"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=IPS, default="v49")
    args = parser.parse_args()
    os.umask(0o077)
    out = ROOT / "logs" / f"{args.target}-first-boot-{time.time_ns()}"
    out.mkdir(mode=0o700)
    events = out / "events.jsonl"
    deadline = time.monotonic() + 600
    last_ports = None
    alpine_samples = 0
    print(json.dumps({"state": "listening", "events": str(events)}), flush=True)
    while time.monotonic() < deadline:
        endpoints = [(ip, port) for ip in IPS[args.target] for port in (22, 2222)
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
                                  "identity": good, "events": str(events)}), flush=True)
                if good and port == 2222:
                    alpine_samples += 1
                    if alpine_samples >= 3:
                        print(json.dumps({"state": f"{args.target}-alpine-observed-3-times",
                                          "events": str(events)}), flush=True)
                        return
            time.sleep(15)
        else:
            time.sleep(3)
    print(json.dumps({"state": "timeout", "events": str(events)}), flush=True)


if __name__ == "__main__":
    main()
