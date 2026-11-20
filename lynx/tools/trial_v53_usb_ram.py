#!/usr/bin/env python3
"""Guarded V53 RAM-only USB mtu3 driver trial; default is offline preparation."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
STOCK = ROOT / "linux-port/artifacts/stock-cph2493-August-eu-ota/vendor-ramdisk-unpacked/lib/modules"
KERNEL = "5.10.149-android12-9-o-g311738fbb5a8"
BOOT_SHA = "c047455271828cf9bfa90984eea121d8ede8754f6297fc06f33f1e99fb23c75e"
MODULES = (
    ("mtu3", "d3c59fa794a6e02f014dd0de660592bb66c9d7f8eb941c1d1183f8a3322bb467"),
)
CONTROLLER_NAME = "11201000.usb0"


def module_plan():
    plan = []
    for name, expected in MODULES:
        path = STOCK / (name + ".ko")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise RuntimeError("stock module hash mismatch: " + name)
        result = subprocess.run(["modinfo", "-F", "vermagic", str(path)],
                                capture_output=True, text=True, timeout=5, check=True)
        if not result.stdout.startswith(KERNEL + " "):
            raise RuntimeError("stock module ABI mismatch: " + name)
        plan.append((name, expected, data))
    return plan


def guard(health):
    battery = health["battery"]
    capacity = battery["capacity_percent"]
    current = battery["current_mA_signed"]
    safe_power = current >= 0 or capacity >= 100
    if (health.get("issues") or not health["wifi"]["carrier"] or
            capacity < 50 or not safe_power or
            battery["temperature_mC"] >= 35000 or health["thermal"]["max_mC"] >= 42000 or
            health["root_free_mib"] < 400 or
            health["root_filesystem"]["ext4_errors_count"] != 0):
        raise RuntimeError("power, thermal, storage, or Wi-Fi guard failed")


def ssh(command, data=None, timeout=20):
    argv = ssh_command("192.168.100.107", command)
    argv[-2:-2] = ["-p", "2222"]
    return subprocess.run(argv, input=data, capture_output=True, timeout=timeout)


def trial(plan):
    out = ROOT / "logs" / ("v53-usb-ram-" + str(time.time_ns()))
    out.mkdir(mode=0o700)
    remote = "/run/lynx-usb-ram-" + str(time.time_ns())
    report = {"state": "preflight", "boot_partition_writes": False,
              "persistent_phone_files": False, "usb_driver": "mtu3",
              "stage": remote, "loaded": [], "steps": [], "watchdog_armed": False,
              "watchdog_cancelled": False}

    def save():
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")

    def step(name, command, data=None, timeout=20):
        start_wall = time.time_ns()
        start_mono = time.monotonic_ns()
        try:
            result = ssh(command, data, timeout)
            code, stdout, stderr = result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired as exc:
            code, stdout, stderr = 124, exc.stdout or b"", exc.stderr or b""
        end_wall = time.time_ns()
        (out / (name + ".stdout")).write_bytes(stdout)
        (out / (name + ".stderr")).write_bytes(stderr)
        report["steps"].append({"name": name, "exit": code,
                                "start_wall_ns": start_wall, "end_wall_ns": end_wall,
                                "elapsed_ms": (time.monotonic_ns() - start_mono) // 1000000})
        save()
        if code:
            raise RuntimeError(name + " failed; see receipt")
        return stdout.decode(errors="replace").strip()

    save()
    try:
        identity = step("identity", "cat /proc/sys/kernel/random/boot_id; uname -r; "
                        "sha256sum /dev/sdc39 | cut -c1-64").splitlines()
        if len(identity) != 3 or identity[1:] != [KERNEL, BOOT_SHA]:
            raise RuntimeError("unexpected boot image or kernel")
        report["boot_id"] = identity[0]
        health = json.loads(step("health_before", "/usr/local/bin/lynx-status --assert-ready"))
        if health["boot_id"] != identity[0]:
            raise RuntimeError("boot changed during preflight")
        guard(health)
        step("interface_before", "set -eu; test -d /sys/bus/platform/devices/" + CONTROLLER_NAME + "; "
             "test ! -e /sys/bus/platform/devices/" + CONTROLLER_NAME + "/driver; "
             "! grep -q '^mtu3 ' /proc/modules; rc-service lynx-wifi status")
        step("stage_dir", "mkdir -m 700 " + remote)
        for name, digest, data in plan:
            target = remote + "/" + name + ".ko"
            step(name + "_stage", "cat > " + target, data, timeout=25)
            step(name + "_verify", "test \"$(sha256sum " + target +
                 " | cut -c1-64)\" = " + digest)
        watchdog = ("#!/bin/sh\nsleep 120\n" +
                    "test -e " + remote + "/cancel && exit 0\n" +
                    "echo reboot > " + remote + "/watchdog-state\n" +
                    "exec /sbin/reboot\n").encode()
        step("watchdog_stage", "cat > " + remote + "/watchdog.sh; chmod 700 " +
             remote + "/watchdog.sh", watchdog)
        step("watchdog_arm", "/usr/bin/setsid /bin/sh " + remote +
             "/watchdog.sh </dev/null >" + remote + "/watchdog.log 2>&1 & " +
             "echo $! > " + remote + "/watchdog.pid; sleep 0.1; " +
             "kill -0 $(cat " + remote + "/watchdog.pid)")
        report["watchdog_armed"] = True
        save()
        for name, _digest, _data in plan:
            report["attempted"] = name
            save()
            step(name + "_load", "/bin/busybox timeout -k 2 12 /sbin/insmod " +
                 remote + "/" + name + ".ko", timeout=18)
            report["loaded"].append(name)
            save()
            step(name + "_post", "set -eu; grep -q '^" + name +
                 " ' /proc/modules; /usr/local/bin/lynx-status --assert-ready; " +
                 "rc-service lynx-wifi status; dmesg | tail -n 100")
        state = step("interface_after",
                     "if test -L /sys/bus/platform/devices/" + CONTROLLER_NAME + "/driver; "
                     "then echo DRIVER_BOUND; else echo DRIVER_UNBOUND; fi; "
                     "echo 'UDCS='$(ls /sys/class/udc 2>/dev/null | tr '\\n' ','); "
                     "dmesg | tail -n 120")
        report["driver_bound"] = "DRIVER_BOUND" in state.splitlines()
        lines = state.splitlines()
        udc_line = next((l for l in lines if l.startswith("UDCS=")), "UDCS=")
        udcs = [u.strip() for u in udc_line.partition("=")[2].split(",") if u.strip()]
        report["udc_devices"] = udcs
        after = json.loads(step("health_after", "/usr/local/bin/lynx-status --assert-ready"))
        if after["boot_id"] != identity[0] or after.get("issues") or not after["wifi"]["carrier"]:
            raise RuntimeError("Alpine health changed after USB mtu3 probe")
        guard(after)
        step("watchdog_cancel", "touch " + remote + "/cancel; test -e " + remote + "/cancel")
        report["watchdog_cancelled"] = True
        report["state"] = "probe-complete-healthy"
    except Exception as exc:
        report.update(state="failed-or-contact-lost", error=str(exc))
        if report["watchdog_armed"]:
            report["watchdog_reboot_expected_within_seconds"] = 120
    finally:
        save()
    print(json.dumps({"state": report["state"], "receipt": str(out / "result.json"),
                      "watchdog_cancelled": report["watchdog_cancelled"],
                      "driver_bound": report.get("driver_bound"),
                      "udc_devices": report.get("udc_devices"),
                      "error": report.get("error")},
                     sort_keys=True))
    return 0 if report["state"] == "probe-complete-healthy" else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", action="store_true", help="run the guarded live trial")
    args = parser.parse_args(argv)
    try:
        plan = module_plan()
    except (OSError, RuntimeError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired) as exc:
        print(json.dumps({"state": "offline-preflight-failed", "error": str(exc)[:200]}))
        return 1
    if not args.start:
        print(json.dumps({"state": "offline-ready", "live_contact": False,
                          "boot_sha256": BOOT_SHA,
                          "modules": [{"name": name, "sha256": digest}
                                      for name, digest, _data in plan]}, sort_keys=True))
        return 0
    return trial(plan)


if __name__ == "__main__":
    sys.exit(main())
