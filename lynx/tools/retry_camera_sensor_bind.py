#!/usr/bin/env python3
"""Retry one failed stock imgsensor probe after its regulators are present."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
DEVICES = ("2-001a", "8-0036", "9-0010", "9-003d")
BOOT = "c047455271828cf9bfa90984eea121d8ede8754f6297fc06f33f1e99fb23c75e"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("device", choices=DEVICES)
    args = parser.parse_args()
    os.umask(0o077)
    out = ROOT / "logs" / f"camera-bind-{args.device}-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "starting", "device": args.device,
              "boot_partition_writes": False, "camera_capture_requested": False,
              "steps": []}

    def step(name, command, timeout=18):
        argv = ssh_command("192.168.100.107", command)
        argv[-2:-2] = ["-p", "2222"]
        result = subprocess.run(argv, capture_output=True, timeout=timeout)
        (out / (name + ".stdout")).write_bytes(result.stdout)
        (out / (name + ".stderr")).write_bytes(result.stderr)
        report["steps"].append({"name": name, "exit": result.returncode})
        if result.returncode:
            raise RuntimeError(f"{name} failed; see receipt")
        return result.stdout.decode(errors="replace").strip()

    try:
        boot = step("boot", "sha256sum /dev/sdc39 | cut -c1-64", timeout=30)
        if boot != BOOT:
            raise RuntimeError("unexpected boot image")
        health = json.loads(step("health_before", "/usr/local/bin/lynx-status --assert-ready"))
        if (health["issues"] or health["battery"]["capacity_percent"] < 50 or
                health["battery"]["temperature_mC"] >= 35000 or
                health["thermal"]["max_mC"] >= 45000):
            raise RuntimeError("health gate failed")
        report["boot_id"] = health["boot_id"]
        step("providers", "set -eu; test -L /sys/bus/i2c/devices/3-002f/driver; "
             "test -L /sys/bus/platform/devices/1b080000.ccu_rproc/driver; "
             f"test ! -L /sys/bus/i2c/devices/{args.device}/driver; "
             "grep -q '^imgsensor ' /proc/modules")
        watchdog = "/run/lynx/camera-ram/watchdog.sh"
        pid = step("arm_watchdog", f"setsid {watchdog} </dev/null "
                   ">>/run/lynx/camera-ram/watchdog.log 2>&1 & echo $!")
        try:
            report["bind_requested"] = True
            step("bind", f"/bin/busybox timeout 20 sh -c "
                 f"'echo {args.device} > /sys/bus/i2c/drivers/imgsensor/bind'", timeout=28)
        finally:
            step("disarm_watchdog", f"kill {pid} 2>/dev/null || true")
        report["driver"] = step("driver", f"readlink /sys/bus/i2c/devices/{args.device}/driver")
        report["nodes"] = step("nodes", "find /dev -maxdepth 1 "
                               "\\( -name 'video*' -o -name 'media*' -o "
                               "-name 'v4l-subdev*' \\) | sort")
        report["dmesg"] = step("dmesg", "dmesg | grep -Ei 'imgsensor|camera' | tail -60")[-6000:]
        after = json.loads(step("health_after", "/usr/local/bin/lynx-status --assert-ready"))
        if after["boot_id"] != report["boot_id"] or after["issues"]:
            raise RuntimeError("post-bind health changed")
        report["state"] = "sensor-bound-no-capture"
    except Exception as exc:
        report.update(state="bind-failed-or-incomplete", error=str(exc))
    (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"], "receipt": str(out / "result.json"),
                      "error": report.get("error")}))
    if report["state"] != "sensor-bound-no-capture":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
