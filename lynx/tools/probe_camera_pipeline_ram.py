#!/usr/bin/env python3
"""Load a bounded prefix of the reviewed camera pipeline in RAM."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "linux-port/camera-pipeline-modules.json"
BOOT = "c047455271828cf9bfa90984eea121d8ede8754f6297fc06f33f1e99fb23c75e"
STAGE = "/run/lynx/camera-pipeline"


def main():
    manifest = json.loads(MANIFEST.read_text())
    order = manifest["order"]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--through", choices=order, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    out = ROOT / "logs" / f"camera-pipeline-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "starting", "through": args.through,
              "boot_partition_writes": False, "capture_requested": False,
              "modules_unloaded": False, "steps": []}

    def save():
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")

    def step(name, command, data=None, timeout=20):
        argv = ssh_command("192.168.100.107", command)
        argv[-2:-2] = ["-p", "2222"]
        result = subprocess.run(argv, input=data, capture_output=True, timeout=timeout)
        (out / (name + ".stdout")).write_bytes(result.stdout)
        (out / (name + ".stderr")).write_bytes(result.stderr)
        report["steps"].append({"name": name, "exit": result.returncode})
        save()
        if result.returncode:
            raise RuntimeError(f"{name} failed; see receipt")
        return result.stdout.decode(errors="replace").strip()

    try:
        if manifest["schema"] != 1 or manifest["kernel"] != "5.10.149-android12-9-o-g311738fbb5a8":
            raise RuntimeError("camera manifest incompatible")
        identity = step("identity", "cat /proc/sys/kernel/random/boot_id; uname -r; "
                        "sha256sum /dev/sdc39 | cut -c1-64", timeout=30).splitlines()
        if len(identity) != 3 or identity[1:] != [manifest["kernel"], BOOT]:
            raise RuntimeError("unexpected boot identity")
        report["boot_id"] = identity[0]
        health = json.loads(step("health_before", "/usr/local/bin/lynx-status --assert-ready"))
        if (health["boot_id"] != identity[0] or health["issues"] or
                health["battery"]["capacity_percent"] < 50 or
                health["battery"]["temperature_mC"] >= 35000 or
                health["thermal"]["max_mC"] >= 45000):
            raise RuntimeError("health gate failed")
        step("providers", "set -eu; test -L /sys/bus/i2c/devices/3-002f/driver; "
             "test -L /sys/bus/platform/devices/1b080000.ccu_rproc/driver; "
             "test -L /sys/bus/i2c/devices/8-0036/driver")
        step("directory", f"mkdir -p {STAGE}; chmod 700 {STAGE}")
        watchdog = f"{STAGE}/watchdog.sh"
        step("watchdog", f"cat > {watchdog}",
             b"#!/bin/sh\nsleep 90\necho camera-pipeline-watchdog-reboot >> /run/lynx/camera-pipeline/watchdog.log\nreboot -f\n")
        step("watchdog_mode", f"chmod 700 {watchdog}")
        for name in order:
            kernel_name = name.replace("-", "_")
            loaded = step("present_" + name,
                          f"if grep -q '^{kernel_name} ' /proc/modules; "
                          "then echo yes; else echo no; fi")
            if loaded != "yes":
                info = manifest["modules"][name]
                source = ROOT / info["path"]
                data = source.read_bytes()
                if hashlib.sha256(data).hexdigest() != info["sha256"]:
                    raise RuntimeError("stock module checksum mismatch: " + name)
                if not info["kernel_matches"]:
                    raise RuntimeError("module kernel mismatch: " + name)
                remote = f"{STAGE}/{name}.ko"
                step("stage_" + name, f"cat > {remote}", data, timeout=40)
                if step("hash_" + name,
                        f"sha256sum {remote} | cut -c1-64") != info["sha256"]:
                    raise RuntimeError("transfer checksum mismatch: " + name)
                pid = step("arm_" + name, f"setsid {watchdog} </dev/null "
                           f">>{STAGE}/watchdog.log 2>&1 & echo $!")
                report["attempting"] = name
                report["watchdog_pid"] = pid
                save()
                try:
                    step("load_" + name,
                         f"/bin/busybox timeout 20 /sbin/insmod {remote}", timeout=28)
                    report.setdefault("loaded", []).append(name)
                    save()
                    step("health_" + name,
                         f"set -eu; grep -q '^{kernel_name} ' /proc/modules; "
                         "/usr/local/bin/lynx-status --assert-ready >/dev/null", timeout=15)
                finally:
                    step("disarm_" + name, f"kill {pid} 2>/dev/null || true")
                    report.pop("watchdog_pid", None)
            if name == args.through:
                break
        report["nodes"] = step("nodes", "find /dev -maxdepth 1 "
                               "\\( -name 'video*' -o -name 'media*' -o "
                               "-name 'v4l-subdev*' \\) | sort")
        report["dmesg"] = step("dmesg", "dmesg | grep -Ei 'camisp|imgsys|remoteproc|camera|ccu' | tail -80")[-8000:]
        report["state"] = "module-prefix-loaded-no-capture"
    except Exception as exc:
        report.update(state="failed-leave-loaded-modules-alone", error=str(exc))
    save()
    print(json.dumps({"state": report["state"], "receipt": str(out / "result.json"),
                      "error": report.get("error")}))
    if report["state"] != "module-prefix-loaded-no-capture":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
