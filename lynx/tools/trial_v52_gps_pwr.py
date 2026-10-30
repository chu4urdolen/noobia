#!/usr/bin/env python3
"""Load the exact stock GPS power module into V52 RAM under a reboot guard."""

import hashlib
import json
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
GRAPH = ROOT / "logs/hardware-dependencies-1793303434757393031.json"
V52_SHA = "9206aafb339ad66b2d942ea5795b8f476a5eaf3a148f9cdfc76be22cb83e30bf"


def phone(command, data=None, timeout=18):
    argv = ssh_command("192.168.100.107", command)
    argv[-2:-2] = ["-p", "2222"]
    return subprocess.run(argv, input=data, capture_output=True, timeout=timeout)


def main():
    module = json.loads(GRAPH.read_text())["modules"]["gps_pwr"]
    data = (ROOT / module["path"]).read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if not module["kernel_matches"] or digest != module["sha256"] or module["depends"] != ["connadp"]:
        raise SystemExit("stock GPS power module preflight failed")
    out = ROOT / "logs" / f"v52-gps-pwr-{time.time_ns()}"
    out.mkdir(mode=0o700)
    remote = "/run/lynx-gps-pwr-trial-" + str(time.time_ns())
    report = {"state": "preflight", "partition_writes": False,
              "module_unload_attempted": False, "remote": remote, "steps": []}
    armed = False
    boot_id = None

    def save():
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")

    def step(name, command, data=None, timeout=18):
        result = phone(command, data, timeout)
        (out / f"{name}.stdout").write_bytes(result.stdout)
        (out / f"{name}.stderr").write_bytes(result.stderr)
        report["steps"].append({"name": name, "exit": result.returncode})
        save()
        if result.returncode:
            raise RuntimeError(name + " failed")
        return result.stdout.decode(errors="replace").strip()

    save()
    try:
        identity = step("identity", "cat /proc/sys/kernel/random/boot_id; "
                        "sha256sum /dev/sdc39 | cut -c1-64").splitlines()
        if len(identity) != 2 or identity[1] != V52_SHA:
            raise RuntimeError("not exact V52 boot")
        boot_id = identity[0]
        report["boot_id"] = boot_id
        health = json.loads(step("health_before", "/usr/local/bin/lynx-status --assert-ready"))
        if (health["boot_id"] != boot_id or health["issues"] or
                health["battery"]["capacity_percent"] < 50 or
                health["battery"]["temperature_mC"] >= 35000 or
                health["thermal"]["max_mC"] >= 45000):
            raise RuntimeError("power or service guard failed")
        step("module_preflight", "set -eu; test -d /sys/module/connadp; "
             "test -d /sys/module/gps_drv_dl_v050; test ! -d /sys/module/gps_pwr; "
             "test ! -e /dev/gps_pwr")
        step("remote_dir", f"mkdir -m 700 {remote}")
        step("module_stage", f"cat > {remote}/gps_pwr.ko; "
             f'test "$(sha256sum {remote}/gps_pwr.ko | cut -c1-64)" = {digest}', data)
        watchdog = ("#!/bin/sh\nsleep 60\n"
                    f"test -e {remote}/cancel && exit 0\n"
                    f"echo reboot > {remote}/watchdog-state\nexec /sbin/reboot\n")
        step("watchdog_stage", f"cat > {remote}/watchdog.sh; chmod 700 {remote}/watchdog.sh",
             watchdog.encode())
        armed = True
        step("watchdog_arm", f"/usr/bin/setsid /bin/sh {remote}/watchdog.sh "
             f"</dev/null >{remote}/watchdog.log 2>&1 & "
             f"echo $! > {remote}/pid; sleep 0.1; kill -0 $(cat {remote}/pid)")
        step("module_load", f"/usr/bin/timeout -k 2 12 insmod {remote}/gps_pwr.ko",
             timeout=18)
        report["node"] = step("node", "ls -l /dev/gps_pwr; test -c /dev/gps_pwr")
        step("kernel_log", "dmesg | tail -n 120")
        after = json.loads(step("health_after", "/usr/local/bin/lynx-status --assert-ready"))
        if after["boot_id"] != boot_id or after["issues"] or not after["wifi"]["carrier"]:
            raise RuntimeError("Alpine health changed")
        report["state"] = "gps-power-node-ready-healthy"
    except Exception as exc:
        report.update(state="failed-or-contact-lost", error=str(exc))
    finally:
        if armed and boot_id:
            try:
                check = phone("cat /proc/sys/kernel/random/boot_id; "
                              "/usr/local/bin/lynx-status --assert-ready; "
                              "! pgrep -x insmod", timeout=8)
                lines = check.stdout.decode(errors="replace").splitlines()
                healthy = (check.returncode == 0 and len(lines) >= 2 and lines[0] == boot_id and
                           not json.loads(lines[1])["issues"])
                if healthy:
                    report["watchdog_cancelled"] = phone(
                        f"touch {remote}/cancel; test -e {remote}/cancel", timeout=8).returncode == 0
            except (OSError, ValueError, subprocess.TimeoutExpired):
                pass
        if armed and not report.get("watchdog_cancelled"):
            report["watchdog_reboot_expected_within_seconds"] = 60
        save()
    print(json.dumps({"state": report["state"], "receipt": str(out / "result.json"),
                      "watchdog_cancelled": report.get("watchdog_cancelled"),
                      "error": report.get("error")}))
    if report["state"] != "gps-power-node-ready-healthy" or not report.get("watchdog_cancelled"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
