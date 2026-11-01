#!/usr/bin/env python3
"""Historical V52 radio-quiesce reboot trial; failed after long uptime.

Not installed on Lynx. The 2026-11-01 guarded trial still returned to
Fastboot before rescue SSH. Retain this source to explain the receipt only.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time


V50_SHA = "6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59"
V52_SHA = "9206aafb339ad66b2d942ea5795b8f476a5eaf3a148f9cdfc76be22cb83e30bf"
LOG = Path("/var/log/lynx/radio-safe-reboot.jsonl")
SETTLE_SECONDS = 60
KERNEL_TIME = re.compile(r"\[\s*(\d+\.\d+)\]")


def run(argv, timeout=15, check=True):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError(f"{argv[0]} returned {result.returncode}")
    return result


def record(event, **fields):
    entry = {"at_unix": int(time.time()), "event": event, **fields}
    LOG.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(LOG, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "a") as target:
        target.write(json.dumps(entry, sort_keys=True) + "\n")
        target.flush()
        os.fsync(target.fileno())
    print(json.dumps(entry, sort_keys=True), flush=True)


def boot_identity():
    digest = run(["sha256sum", "/dev/sdc39"], timeout=25).stdout.split()[0]
    if digest not in (V50_SHA, V52_SHA):
        raise RuntimeError("boot_a hash is not a verified V50/V52 image")
    return digest


def health():
    status = json.loads(run(["/usr/local/bin/lynx-status", "--assert-ready"],
                            timeout=12).stdout)
    if status["issues"] or status["battery"]["capacity_percent"] < 20 or \
            status["thermal"]["max_mC"] >= 55000:
        raise RuntimeError("Alpine, battery, or thermal preflight failed")
    return status


def running():
    return run(["rc-service", "lynx-bluetooth", "status"],
               timeout=8, check=False).returncode == 0


def radio_absent():
    return (not running() and not Path("/sys/class/bluetooth/hci0").exists()
            and not Path("/run/lynx/bluetooth/ready").exists())


def kernel_poweroff_since(uptime):
    output = run(["dmesg"], timeout=10).stdout
    for line in output.splitlines():
        if "conninfra_pwr_off" not in line or "drv=[0]" not in line:
            continue
        match = KERNEL_TIME.search(line)
        if match and float(match.group(1)) >= uptime - 1:
            return True
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--reboot", action="store_true")
    parser.add_argument("--experimental-repeat", action="store_true")
    args = parser.parse_args()
    if args.check == args.reboot:
        parser.error("select exactly one of --check or --reboot")
    if args.reboot and not args.experimental_repeat:
        parser.error("the radio-quiesce reboot trial failed; explicit --experimental-repeat required")
    if os.geteuid() != 0:
        raise SystemExit("root required")
    digest = boot_identity()
    status = health()
    if "lynx-bluetooth" in run(["rc-update", "show", "default"],
                                timeout=8).stdout:
        raise RuntimeError("Bluetooth autostart is enabled; reboot refused")
    was_running = running()
    if args.check:
        print(json.dumps({"state": "eligible", "boot_sha256": digest,
                          "boot_id": status["boot_id"],
                          "bluetooth_running": was_running,
                          "radio_absent": radio_absent(),
                          "battery_percent": status["battery"]["capacity_percent"]}))
        return
    record("preflight", boot_sha256=digest, boot_id=status["boot_id"],
           bluetooth_running=was_running)
    if was_running:
        if digest != V52_SHA:
            raise RuntimeError("Bluetooth running on unexpected boot image")
        before = float(Path("/proc/uptime").read_text().split()[0])
        run(["rc-service", "lynx-bluetooth", "stop"], timeout=25)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if radio_absent() and kernel_poweroff_since(before):
                break
            time.sleep(1)
        else:
            raise RuntimeError("Bluetooth kernel power-off was not confirmed")
        record("radio-power-off-confirmed", uptime_before_stop=before)
        time.sleep(SETTLE_SECONDS)
    if not radio_absent():
        raise RuntimeError("radio still present")
    after = health()
    if after["boot_id"] != status["boot_id"]:
        raise RuntimeError("boot changed during shutdown preparation")
    record("requesting-reboot", settle_seconds=SETTLE_SECONDS if was_running else 0)
    run(["sync"], timeout=20)
    run(["/sbin/openrc-shutdown", "-r", "now"], timeout=8)


if __name__ == "__main__":
    main()
