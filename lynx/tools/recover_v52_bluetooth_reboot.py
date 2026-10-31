#!/usr/bin/env python3
"""Reboot Lynx from Fastboot once, then disable unverified BT autostart over SSH."""

import json
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command
from lynx_fastboot_preflight import FASTBOOT, SERIAL


ROOT = Path(__file__).resolve().parent.parent


def fastboot(*arguments):
    return subprocess.run(["sudo", "-n", str(FASTBOOT), "-s", SERIAL, *arguments],
                          capture_output=True, text=True, timeout=12)


def phone(command, timeout=8):
    argv = ssh_command("192.168.100.107", command)
    argv[-2:-2] = ["-p", "2222"]
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)


def main():
    receipt = ROOT / "logs" / f"v52-bt-fastboot-recovery-{time.time_ns()}"
    receipt.mkdir(mode=0o700)
    report = {"state": "preflight", "partition_writes": False, "steps": []}

    def save():
        (receipt / "result.json").write_text(json.dumps(report, indent=2) + "\n")

    def record(name, result):
        (receipt / (name + ".stdout")).write_text(result.stdout)
        (receipt / (name + ".stderr")).write_text(result.stderr)
        report["steps"].append({"name": name, "exit": result.returncode})
        save()
        return result.stdout + result.stderr

    try:
        expected = {"product": "k6983v1_64", "current-slot": "a",
                    "slot-successful:a": "yes", "slot-unbootable:a": "no"}
        for name, value in expected.items():
            result = fastboot("getvar", name)
            output = record("getvar_" + name.replace(":", "_"), result)
            if result.returncode or f"{name}: {value}" not in output:
                raise RuntimeError("Fastboot identity or bootability changed: " + name)
        reboot = fastboot("reboot")
        record("fastboot_reboot", reboot)
        if reboot.returncode:
            raise RuntimeError("Fastboot reboot rejected")
        report["state"] = "waiting-for-alpine"
        save()
        deadline = time.monotonic() + 360
        while time.monotonic() < deadline:
            try:
                result = phone("cat /proc/sys/kernel/random/boot_id; "
                               "/usr/local/bin/lynx-status --assert-ready", timeout=5)
                if result.returncode == 0:
                    record("alpine_returned", result)
                    lines = result.stdout.splitlines()
                    report["boot_id"] = lines[0]
                    report["health"] = json.loads(lines[1])
                    break
            except (OSError, subprocess.TimeoutExpired, ValueError, IndexError):
                pass
            time.sleep(2)
        else:
            try:
                report["fastboot_after_timeout"] = (fastboot("getvar", "current-slot")
                                                    .returncode == 0)
            except (OSError, subprocess.TimeoutExpired):
                report["fastboot_after_timeout"] = False
            raise RuntimeError("Alpine SSH did not return within 360 seconds")
        logs = phone("tail -90 /var/log/lynx-bluetoothd.log; "
                     "cat /var/log/lynx-bt-firstboot-guard.log 2>/dev/null || true; "
                     "rc-service lynx-bluetooth status; "
                     "rc-update show default | grep -E 'lynx-bluetooth|lynx-bt-firstboot-guard'",
                     timeout=10)
        record("boot_evidence", logs)
        disable = phone("set -eu; rc-update del lynx-bluetooth default || true; "
                        "rc-service lynx-bluetooth stop || true; "
                        "mkdir -p /run/lynx-bt-firstboot-guard; "
                        "touch /run/lynx-bt-firstboot-guard/cancel; "
                        "rc-update del lynx-bt-firstboot-guard default || true; "
                        "rm -f /etc/init.d/lynx-bt-firstboot-guard; "
                        "! rc-update show default | grep -q lynx-bluetooth; "
                        "/usr/local/bin/lynx-status --assert-ready", timeout=20)
        record("disable_bluetooth_autostart", disable)
        if disable.returncode:
            raise RuntimeError("Alpine returned but Bluetooth autostart rollback failed")
        report["state"] = "alpine-healthy-bluetooth-autostart-disabled"
    except Exception as exc:
        report.update(state="failed", error=str(exc))
    save()
    print(json.dumps({"state": report["state"], "receipt": str(receipt / "result.json"),
                      "error": report.get("error")}))
    if report["state"] != "alpine-healthy-bluetooth-autostart-disabled":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
