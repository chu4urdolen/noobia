#!/usr/bin/env python3
"""Guarded RAM-only GNSS data-link trial after a successful V52 Bluetooth probe."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
GRAPH = ROOT / "logs/hardware-dependencies-1793303434757393031.json"
V52_SHA = "9206aafb339ad66b2d942ea5795b8f476a5eaf3a148f9cdfc76be22cb83e30bf"
KERNEL = "5.10.149-android12-9-o-g311738fbb5a8"
MODULES = ("gps_drv_dl_v050",)
PROBE = '''#!/usr/bin/env python3
import json, os, time
path = "/dev/gpsdl0"
result = {"path": path, "opened": False}
fd = None
try:
    started = time.monotonic()
    fd = os.open(path, os.O_RDWR | os.O_NONBLOCK | os.O_CLOEXEC)
    result["opened"] = True
    result["open_seconds"] = round(time.monotonic() - started, 3)
except OSError as exc:
    result["error"] = {"errno": exc.errno, "message": exc.strerror}
finally:
    if fd is not None:
        os.close(fd)
print(json.dumps(result))
'''


def phone(command, data=None, timeout=18):
    argv = ssh_command("192.168.100.107", command)
    argv[-2:-2] = ["-p", "2222"]
    return subprocess.run(argv, input=data, capture_output=True, timeout=timeout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bt-receipt", type=Path, required=True,
                        help="successful V52 HCI trial receipt from the same boot")
    args = parser.parse_args()
    source_receipt = args.bt_receipt.resolve(strict=True)
    if not source_receipt.is_relative_to(ROOT / "logs"):
        parser.error("BT receipt must be under Lynx logs")
    bt = json.loads(source_receipt.read_text())
    if bt.get("state") != "hci-commands-complete-healthy" or not bt.get("watchdog_cancelled"):
        parser.error("successful V52 HCI receipt required")
    graph = json.loads(GRAPH.read_text())["modules"]
    stock = {}
    for name in MODULES:
        info = graph[name]
        data = (ROOT / info["path"]).read_bytes()
        if not info["kernel_matches"] or hashlib.sha256(data).hexdigest() != info["sha256"]:
            parser.error("stock GNSS module changed: " + name)
        stock[name] = (data, info["sha256"])

    out = ROOT / "logs" / f"v52-gnss-link-{time.time_ns()}"
    out.mkdir(mode=0o700)
    remote = "/run/lynx-gnss-link-" + str(time.time_ns())
    report = {"state": "preflight", "bt_receipt": str(source_receipt),
              "boot_partition_writes": False, "module_unload_attempted": False,
              "position_fix": False, "remote": remote, "steps": []}
    armed = False

    def save():
        temp = out / "result.tmp"
        temp.write_text(json.dumps(report, indent=2) + "\n")
        temp.replace(out / "result.json")

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
                        "uname -r; sha256sum /dev/sdc39 | cut -c1-64").splitlines()
        if (len(identity) != 3 or identity[1:] != [KERNEL, V52_SHA] or
                identity[0] != bt.get("boot_id")):
            raise RuntimeError("V52 boot differs from successful Bluetooth trial")
        report["boot_id"] = identity[0]
        health = json.loads(step("health_before", "/usr/local/bin/lynx-status --assert-ready"))
        if (health["boot_id"] != identity[0] or health["issues"] or
                health["battery"]["capacity_percent"] < 50 or
                health["battery"]["temperature_mC"] >= 35000 or
                health["thermal"]["max_mC"] >= 45000):
            raise RuntimeError("power or service health guard failed")
        step("module_preflight", "set -eu; rc-service lynx-wifi status; "
             "test -d /sys/module/conninfra; "
             "test ! -d /sys/module/gps_drv_dl_v050")
        step("remote_dir", f"mkdir -m 700 {remote}")
        for name in MODULES:
            data, digest = stock[name]
            step("stage_" + name, f"cat > {remote}/{name}.ko; "
                 f'test "$(sha256sum {remote}/{name}.ko | cut -c1-64)" = {digest}', data)
        probe = PROBE.encode()
        digest = hashlib.sha256(probe).hexdigest()
        step("probe_stage", f"cat > {remote}/probe.py; "
             f'test "$(sha256sum {remote}/probe.py | cut -c1-64)" = {digest}; '
             f"/usr/bin/python3 -m py_compile {remote}/probe.py", probe)
        watchdog = ("#!/bin/sh\n"
                    "sleep 90\n"
                    f"test -e {remote}/cancel && exit 0\n"
                    f"echo watchdog-reboot > {remote}/state\n"
                    "exec /sbin/reboot\n")
        step("watchdog_stage", f"cat > {remote}/watchdog.sh; "
             f"chmod 700 {remote}/watchdog.sh; /bin/sh -n {remote}/watchdog.sh",
             watchdog.encode())
        armed = True
        step("watchdog_arm", f"/usr/bin/setsid /bin/sh {remote}/watchdog.sh "
             f"</dev/null >{remote}/watchdog.log 2>&1 & "
             f"echo $! > {remote}/pid; sleep 0.1; kill -0 $(cat {remote}/pid)")
        report["state"] = "watchdog-armed"
        save()
        for name in MODULES:
            step("load_" + name, f"/usr/bin/timeout -k 2 12 /sbin/insmod "
                 f"{remote}/{name}.ko", timeout=18)
        step("device_node", "set -eu; /bin/busybox mdev -s; "
             "test -d /sys/module/gps_drv_dl_v050; test -c /dev/gpsdl0")
        raw = step("link_probe", f"/usr/bin/timeout -k 2 10 "
                   f"/usr/bin/python3 {remote}/probe.py", timeout=17)
        report["probe"] = json.loads(raw)
        if not report["probe"].get("opened"):
            raise RuntimeError("GNSS link did not open")
        after = json.loads(step("health_after", "/usr/local/bin/lynx-status --assert-ready"))
        if after["boot_id"] != identity[0] or after["issues"] or not after["wifi"]["carrier"]:
            raise RuntimeError("Alpine health changed during GNSS trial")
        step("kernel_log", "dmesg | tail -n 150")
        report["state"] = "gnss-link-opened-no-position"
    except Exception as exc:
        report.update(state="failed-or-contact-lost", error=str(exc))
    finally:
        if armed and report["state"] == "gnss-link-opened-no-position":
            try:
                cancelled = phone(f"touch {remote}/cancel; test -e {remote}/cancel", timeout=8)
                report["watchdog_cancelled"] = cancelled.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                report["watchdog_cancelled"] = False
        if armed and not report.get("watchdog_cancelled"):
            report["watchdog_reboot_expected_within_seconds"] = 90
        save()
    print(json.dumps({"state": report["state"], "receipt": str(out / "result.json"),
                      "watchdog_cancelled": report.get("watchdog_cancelled"),
                      "error": report.get("error")}))
    if report["state"] != "gnss-link-opened-no-position" or not report.get("watchdog_cancelled"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
