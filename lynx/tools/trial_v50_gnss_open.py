#!/usr/bin/env python3
"""Bounded, RAM-only GPS data-link open/read with a reboot fallback."""

import json
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
BOOT = "6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59"
KERNEL = "5.10.149-android12-9-o-g311738fbb5a8"

PROBE = '''#!/usr/bin/env python3
import json, os, select, time
path = "/dev/gpsdl0"
result = {"path": path, "opened": False, "bytes_read": 0}
fd = None
try:
    start = time.monotonic()
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
    result["opened"] = True
    result["open_seconds"] = round(time.monotonic() - start, 3)
    ready, _, _ = select.select([fd], [], [], 8)
    if ready:
        data = os.read(fd, 2048)
        result["bytes_read"] = len(data)
        result["sample_hex"] = data[:128].hex()
        result["sample_text"] = data[:128].decode("ascii", errors="replace")
    else:
        result["read_timeout_seconds"] = 8
except OSError as exc:
    result["error"] = {"errno": exc.errno, "message": exc.strerror}
finally:
    if fd is not None:
        os.close(fd)
print(json.dumps(result))
'''


def phone(command, data=None, timeout=18):
    args = ssh_command("192.168.100.107", command)
    args[-2:-2] = ["-p", "2222"]
    return subprocess.run(args, input=data, capture_output=True, timeout=timeout)


def main():
    receipt = ROOT / "logs" / f"v50-gnss-open-{time.time_ns()}"
    receipt.mkdir(mode=0o700)
    watchdog = "/run/lynx-gnss-open-" + str(time.time_ns())
    report = {"state": "preflight", "boot_partition_writes": False,
              "watchdog_directory": watchdog, "steps": []}
    armed = False

    def save():
        (receipt / "result.json").write_text(json.dumps(report, indent=2) + "\n")

    def step(name, command, data=None, timeout=18):
        try:
            result = phone(command, data, timeout)
        except subprocess.TimeoutExpired:
            report["steps"].append({"name": name, "timeout": True})
            save()
            raise RuntimeError(name + " timed out") from None
        (receipt / (name + ".stdout")).write_bytes(result.stdout)
        (receipt / (name + ".stderr")).write_bytes(result.stderr)
        report["steps"].append({"name": name, "exit": result.returncode})
        save()
        if result.returncode:
            raise RuntimeError(name + " failed")
        return result.stdout.decode(errors="replace").strip()

    try:
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
            raise RuntimeError("Alpine or power health guard failed")
        step("preflight", "set -eu; test -d /sys/module/gps_drv_dl_v050; "
             "test -c /dev/gpsdl0; rc-service lynx-wifi status")
        step("watchdog_dir", f"mkdir -m 700 {watchdog}")
        script = ("#!/bin/sh\n"
                  "sleep 90\n"
                  f"test -e {watchdog}/cancel && exit 0\n"
                  f"echo watchdog-reboot > {watchdog}/state\n"
                  "exec /sbin/reboot\n")
        step("watchdog_stage", f"cat > {watchdog}/watchdog.sh; "
             f"chmod 700 {watchdog}/watchdog.sh; /bin/sh -n {watchdog}/watchdog.sh",
             script.encode())
        step("probe_stage", f"cat > {watchdog}/probe.py; "
             f"/usr/bin/python3 -m py_compile {watchdog}/probe.py", PROBE.encode())
        step("watchdog_arm", f"/usr/bin/setsid /bin/sh {watchdog}/watchdog.sh "
             f"</dev/null >{watchdog}/watchdog.log 2>&1 & "
             f"echo $! > {watchdog}/pid; sleep 0.1; kill -0 $(cat {watchdog}/pid)")
        armed = True
        report["state"] = "watchdog-armed"
        save()
        report["probe"] = json.loads(step("probe", f"/usr/bin/timeout -k 2 25 "
                                          f"/usr/bin/python3 {watchdog}/probe.py", timeout=32))
        after = json.loads(step("health_after", "/usr/local/bin/lynx-status --assert-ready"))
        if after["boot_id"] != identity[0] or after["issues"] or not after["wifi"]["carrier"]:
            raise RuntimeError("Alpine or Wi-Fi changed")
        step("kernel_log", "dmesg | tail -n 100")
        report["state"] = "probe-completed-healthy"
    except Exception as exc:
        report.update(state="failed-or-contact-lost", error=str(exc))
    finally:
        if armed and report["state"] == "probe-completed-healthy":
            try:
                result = phone(f"touch {watchdog}/cancel; test -e {watchdog}/cancel", timeout=8)
                report["watchdog_cancelled"] = result.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                report["watchdog_cancelled"] = False
        if armed and not report.get("watchdog_cancelled"):
            report["watchdog_reboot_expected_within_seconds"] = 90
            if report["state"] == "probe-completed-healthy":
                report["state"] = "watchdog-not-cancelled"
        save()
    print(json.dumps({"state": report["state"], "probe": report.get("probe"),
                      "watchdog_cancelled": report.get("watchdog_cancelled"),
                      "receipt": str(receipt / "result.json"), "error": report.get("error")}))
    if report["state"] != "probe-completed-healthy":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
