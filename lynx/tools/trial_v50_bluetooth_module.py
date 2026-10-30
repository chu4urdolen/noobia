#!/usr/bin/env python3
"""Load one matching Bluetooth module in RAM with a timed reboot fallback."""

import argparse
import json
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
STAGED = ROOT / "logs/v50-hardware-modules-staged-1793305118730077737.json"
BOOT = "6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59"
KERNEL = "5.10.149-android12-9-o-g311738fbb5a8"


def phone(command, data=None, timeout=18):
    args = ssh_command("192.168.100.107", command)
    args[-2:-2] = ["-p", "2222"]
    return subprocess.run(args, input=data, capture_output=True, timeout=timeout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("module", choices=("btif_drv", "bt_drv_6983"))
    args = parser.parse_args()
    receipt = ROOT / "logs" / f"v50-bluetooth-{args.module}-{time.time_ns()}"
    receipt.mkdir(mode=0o700)
    watchdog = "/run/lynx-bt-probe-" + str(time.time_ns())
    report = {"state": "preflight", "module": args.module,
              "watchdog_directory": watchdog, "boot_partition_writes": False,
              "module_unload_attempted": False, "steps": []}
    armed = False

    def save():
        (receipt / "result.json").write_text(json.dumps(report, indent=2) + "\n")

    def step(name, command, data=None, timeout=18):
        started = time.monotonic()
        try:
            result = phone(command, data, timeout)
        except subprocess.TimeoutExpired:
            report["steps"].append({"name": name, "timeout": True,
                                    "elapsed": round(time.monotonic() - started, 2)})
            save()
            raise RuntimeError(name + " timed out") from None
        (receipt / (name + ".stdout")).write_bytes(result.stdout)
        (receipt / (name + ".stderr")).write_bytes(result.stderr)
        report["steps"].append({"name": name, "exit": result.returncode,
                                "elapsed": round(time.monotonic() - started, 2)})
        save()
        if result.returncode:
            raise RuntimeError(name + " failed")
        return result.stdout.decode(errors="replace").strip()

    try:
        staged = json.loads(STAGED.read_text())
        if staged["state"] != "staged-in-ram-not-loaded":
            raise RuntimeError("verified RAM module stage absent")
        manifest = {item["module"]: item for item in staged["files"]}
        item = manifest[args.module]
        identity = step("identity", "cat /proc/sys/kernel/random/boot_id; "
                        "uname -r; sha256sum /dev/sdc39 | cut -c1-64").splitlines()
        if len(identity) != 3 or identity[1:] != [KERNEL, BOOT]:
            raise RuntimeError("V50 identity changed")
        report["boot_id"] = identity[0]
        health = json.loads(step("health_before", "/usr/local/bin/lynx-status --assert-ready"))
        if (health["boot_id"] != identity[0] or health["issues"] or
            health["battery"]["capacity_percent"] < 50 or
            health["battery"]["temperature_mC"] >= 35000 or
            health["thermal"]["max_mC"] >= 45000):
            raise RuntimeError("battery, thermal, or Alpine health guard failed")
        dependency_check = ("test -d /sys/module/btif_drv" if args.module == "bt_drv_6983"
                            else "test ! -d /sys/module/bt_drv_6983")
        step("module_preflight", "set -eu; rc-service lynx-wifi status; "
             + "test ! -d /sys/module/" + args.module + "; "
             + f'test "$(sha256sum {item["remote"]} | cut -c1-64)" = {item["sha256"]}; '
             + dependency_check)
        step("watchdog_dir", f"mkdir -m 700 {watchdog}")
        watchdog_source = ("#!/bin/sh\n"
                           "sleep 90\n"
                           f"test -e {watchdog}/cancel && exit 0\n"
                           f"echo watchdog-reboot > {watchdog}/state\n"
                           "exec /sbin/reboot\n")
        step("watchdog_stage", f"cat > {watchdog}/watchdog.sh; "
             f"chmod 700 {watchdog}/watchdog.sh; "
             f"/bin/sh -n {watchdog}/watchdog.sh", watchdog_source.encode())
        step("watchdog_arm", f"/usr/bin/setsid /bin/sh {watchdog}/watchdog.sh "
             f"</dev/null >{watchdog}/watchdog.log 2>&1 & "
             f"echo $! > {watchdog}/pid; sleep 0.1; "
             f"kill -0 $(cat {watchdog}/pid)")
        armed = True
        report["state"] = "watchdog-armed"
        save()
        step("module_load", f"/usr/bin/timeout -k 2 12 /sbin/insmod {item['remote']}",
             timeout=18)
        report["state"] = "module-loaded-in-ram"
        save()
        step("module_and_health", "set -eu; test -d /sys/module/" + args.module + "; "
             "rc-service lynx-wifi status; /usr/local/bin/lynx-status --assert-ready >/dev/null; "
             "if test -d /sys/class/bluetooth; then "
             "find /sys/class/bluetooth -maxdepth 1 -name 'hci*'; fi; "
             "dmesg | tail -n 70")
        report["state"] = "module-loaded-healthy"
    except Exception as exc:
        report.update(state="failed-or-contact-lost", error=str(exc))
    finally:
        if armed and report["state"] == "module-loaded-healthy":
            try:
                result = phone(f"touch {watchdog}/cancel; test -e {watchdog}/cancel", timeout=8)
                report["watchdog_cancelled"] = result.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                report["watchdog_cancelled"] = False
        if armed and not report.get("watchdog_cancelled"):
            report["watchdog_reboot_expected_within_seconds"] = 90
            if report["state"] == "module-loaded-healthy":
                report["state"] = "watchdog-not-cancelled"
        save()
    print(json.dumps({"state": report["state"], "module": args.module,
                      "watchdog_cancelled": report.get("watchdog_cancelled"),
                      "receipt": str(receipt / "result.json"), "error": report.get("error")}))
    if report["state"] != "module-loaded-healthy":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
