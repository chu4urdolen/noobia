#!/usr/bin/env python3
"""Guarded V53 RAM-only NFC driver probe; default is offline preparation."""

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
    ("oplus_nfc", "4ab0e019dceb426f8bf435a8ea21a40f71ec3f7809441a78e997f37fdd34f940"),
    ("nfc_i2c", "042f949ba0b4ddf5ee4d1ae143be407d1df1cc5be53518cce43e13c1acb67896"),
)


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
    if (health.get("issues") or not health["wifi"]["carrier"] or
            battery["capacity_percent"] < 50 or battery["current_mA_signed"] <= 0 or
            battery["temperature_mC"] >= 35000 or health["thermal"]["max_mC"] >= 42000 or
            health["root_free_mib"] < 400 or
            health["root_filesystem"]["ext4_errors_count"] != 0):
        raise RuntimeError("power, thermal, storage, or Wi-Fi guard failed")


def ssh(command, data=None, timeout=20):
    argv = ssh_command("192.168.100.107", command)
    argv[-2:-2] = ["-p", "2222"]
    return subprocess.run(argv, input=data, capture_output=True, timeout=timeout)


def trial(plan):
    out = ROOT / "logs" / ("v53-nfc-ram-" + str(time.time_ns()))
    out.mkdir(mode=0o700)
    remote = "/run/lynx-nfc-ram-" + str(time.time_ns())
    report = {"state": "preflight", "boot_partition_writes": False,
              "persistent_phone_files": False, "radio_transaction_requested": False,
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
        step("interface_before", "set -eu; test -e /sys/bus/platform/devices/odm:nfc_chipset; "
             "test ! -e /sys/bus/platform/devices/odm:nfc_chipset/driver; "
             "test ! -e /dev/nq-nci; grep -q 'oplus-nfc-chipset' "
             "/sys/bus/platform/devices/odm:nfc_chipset/of_node/compatible; "
             "grep -q '^oplus_project ' /proc/modules; "
             "! grep -q '^oplus_nfc ' /proc/modules; "
             "! grep -q '^nfc_i2c ' /proc/modules; rc-service lynx-wifi status")
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
        state = step("interface_after", "if test -L /sys/bus/platform/devices/odm:nfc_chipset/driver; "
                     "then echo DRIVER_BOUND; else echo DRIVER_UNBOUND; fi; "
                     "if test -e /dev/nq-nci; then echo NQ_NODE; else echo NO_NQ_NODE; fi; "
                     "dmesg | tail -n 120")
        report["driver_bound"] = "DRIVER_BOUND" in state.splitlines()
        report["nq_node"] = "NQ_NODE" in state.splitlines()
        after = json.loads(step("health_after", "/usr/local/bin/lynx-status --assert-ready"))
        if after["boot_id"] != identity[0] or after.get("issues") or not after["wifi"]["carrier"]:
            raise RuntimeError("Alpine health changed after NFC probe")
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
                      "nq_node": report.get("nq_node"), "error": report.get("error")},
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
