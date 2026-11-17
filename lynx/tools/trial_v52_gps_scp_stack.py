#!/usr/bin/env python3
"""Load exact stock SCP/GPS modules into V52 RAM, one by one, with guard logs."""

import hashlib
import json
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
GRAPH = ROOT / "logs/hardware-dependencies-1793303434757393031.json"
V52_SHA = "9206aafb339ad66b2d942ea5795b8f476a5eaf3a148f9cdfc76be22cb83e30bf"
ORDER = ("mtk-mbox", "mtk_rpmsg_mbox", "mtk_tinysys_ipi", "kernel_fb",
         "mtk-afe-external", "scp", "connscp", "gps_scp")


def phone(command, data=None, timeout=18):
    argv = ssh_command("192.168.100.107", command)
    argv[-2:-2] = ["-p", "2222"]
    return subprocess.run(argv, input=data, capture_output=True, timeout=timeout)


def main():
    graph = json.loads(GRAPH.read_text())["modules"]
    modules = {}
    for name in ORDER:
        info = graph[name]
        data = (ROOT / info["path"]).read_bytes()
        if not info["kernel_matches"] or hashlib.sha256(data).hexdigest() != info["sha256"]:
            raise SystemExit("stock module changed: " + name)
        modules[name] = (data, info)
    out = ROOT / "logs" / f"v52-gps-scp-stack-{time.time_ns()}"
    out.mkdir(mode=0o700)
    remote = "/run/lynx-gps-scp-stack-" + str(time.time_ns())
    report = {"state": "preflight", "partition_writes": False,
              "module_unload_attempted": False, "remote": remote,
              "order": list(ORDER), "steps": []}
    boot_id = None
    armed = False

    def save():
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")

    def step(name, command, data=None, timeout=18):
        try:
            result = phone(command, data, timeout)
        except subprocess.TimeoutExpired as exc:
            (out / f"{name}.stdout").write_bytes(exc.stdout or b"")
            (out / f"{name}.stderr").write_bytes(exc.stderr or b"")
            report["steps"].append({"name": name, "timeout": True})
            save()
            raise RuntimeError(name + " timed out") from None
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
             "test -d /sys/module/gps_drv_dl_v050; test -d /sys/module/gps_pwr; "
             "test -c /dev/gps_pwr; test ! -e /dev/gps2scp")
        for name in ORDER:
            sysname = name.replace("-", "_")
            step("absent_" + sysname, f"test ! -d /sys/module/{sysname}")
        step("remote_dir", f"mkdir -m 700 {remote}")
        for name in ORDER:
            data, info = modules[name]
            step("stage_" + name.replace("-", "_"),
                 f"cat > {remote}/{name}.ko; "
                 f'test "$(sha256sum {remote}/{name}.ko | cut -c1-64)" = {info["sha256"]}', data)
        watchdog = ("#!/bin/sh\nsleep 100\n"
                    f"test -e {remote}/cancel && exit 0\n"
                    f"echo reboot > {remote}/watchdog-state\nexec /sbin/reboot\n")
        step("watchdog_stage", f"cat > {remote}/watchdog.sh; chmod 700 {remote}/watchdog.sh",
             watchdog.encode())
        armed = True
        step("watchdog_arm", f"/usr/bin/setsid /bin/sh {remote}/watchdog.sh "
             f"</dev/null >{remote}/watchdog.log 2>&1 & "
             f"echo $! > {remote}/pid; sleep 0.1; kill -0 $(cat {remote}/pid)")
        report["state"] = "loading"
        save()
        for name in ORDER:
            sysname = name.replace("-", "_")
            step("load_" + sysname,
                 f"/usr/bin/timeout -k 2 12 insmod {remote}/{name}.ko; "
                 f"test -d /sys/module/{sysname}", timeout=18)
            after = json.loads(step("health_" + sysname,
                                    "/usr/local/bin/lynx-status --assert-ready"))
            if after["boot_id"] != boot_id or after["issues"] or not after["wifi"]["carrier"]:
                raise RuntimeError("Alpine health changed after " + name)
            step("dmesg_" + sysname, "dmesg | tail -n 80")
        report["gps2scp_node"] = step("gps2scp_node", "ls -l /dev/gps2scp; test -c /dev/gps2scp")
        report["state"] = "gps-scp-node-ready-healthy"
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
            report["watchdog_reboot_expected_within_seconds"] = 100
        save()
    print(json.dumps({"state": report["state"], "receipt": str(out / "result.json"),
                      "watchdog_cancelled": report.get("watchdog_cancelled"),
                      "error": report.get("error")}))
    if report["state"] != "gps-scp-node-ready-healthy" or not report.get("watchdog_cancelled"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
