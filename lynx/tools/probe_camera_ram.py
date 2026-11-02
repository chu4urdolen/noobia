#!/usr/bin/env python3
"""Probe stock camera modules one at a time in RAM, with reboot fallback."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "linux-port/artifacts/stock-cph2493-August-eu-ota"
VENDOR = BASE / "wifi-reference/vendor-dlkm-unpacked/lib/modules"
RAMDISK = BASE / "vendor-ramdisk-unpacked/lib/modules"
MODULES = (
    ("multi_regulator", "4a85c99c5d8498e37e60e72e6d470f72e3fe6cda5663da9af81e4cb8da1269ea", RAMDISK),
    ("clk-mt6983-ccu_main", "9b0bbb0abd17c712f34fee7df3f5910f23aa113949d894ddf2a1b9709b1e4d02", RAMDISK),
    ("mtk_ccu", "f5c986197ebf232e2abc9aafdc5cc8c48a245ea279760d2f65773350df75b991", VENDOR),
    ("v4l2-fwnode", "777631db73fc129294eaf339ecbb13b5a61884ee55ffc377a59945828119ea07", VENDOR),
    ("imgsensor-glue", "c42aa1009f5dda1735c98a10e5884a7fc6036b2014fba25cecfe482c22f5b1be", VENDOR),
    ("kernel_fb", "d9c0e2546e6af4716e76c539bfe3339c9b52cbc4f88aa7c4c33717ad6201fade", RAMDISK),
    ("oplus_cam_event_report", "cbb5325fc2cb77b1a68807a2648f4443321c701a67ca81032aa4407368ffd860", VENDOR),
    ("imgsensor", "4d26ef01b7b1a3be5a597005aa88cd3d1494bcb6fd7c483fd0da9949e50461a1", VENDOR),
    ("camera_eeprom", "e463b6b53173d4b79296ee507072d73b5ec826a4659a39fb40c471aa54055985", VENDOR),
    ("mtk-cam-plat-util", "317e3d214609ca8cd1c0b86340a1a0955e4bd90399f9b0c439781a9524dab6ac", VENDOR),
    ("mtk-cam-plat-mt6983", "51a786cec66039084bd691d5831485abfe73937d96df48552c23031f09a88d32", VENDOR),
)
KERNEL = "5.10.149-android12-9-o-g311738fbb5a8"
BOOT = "c047455271828cf9bfa90984eea121d8ede8754f6297fc06f33f1e99fb23c75e"
STAGE = "/run/lynx/camera-ram"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--through", choices=[item[0] for item in MODULES],
                        required=True)
    args = parser.parse_args()
    os.umask(0o077)
    out = ROOT / "logs" / f"camera-ram-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "starting", "through": args.through,
              "boot_partition_writes": False, "camera_capture_requested": False,
              "modules_unloaded": False, "steps": []}

    def save():
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")

    def step(name, command, data=None, timeout=20):
        command_args = ssh_command("192.168.100.107", command)
        command_args[-2:-2] = ["-p", "2222"]
        result = subprocess.run(command_args, input=data, capture_output=True,
                                timeout=timeout)
        (out / (name + ".stdout")).write_bytes(result.stdout)
        (out / (name + ".stderr")).write_bytes(result.stderr)
        report["steps"].append({"name": name, "exit": result.returncode})
        save()
        if result.returncode:
            raise RuntimeError(f"{name} failed; see receipt")
        return result.stdout.decode(errors="replace").strip()

    try:
        identity = step("identity", "cat /proc/sys/kernel/random/boot_id; uname -r; "
                        "sha256sum /dev/sdc39 | cut -c1-64", timeout=30).splitlines()
        if len(identity) != 3 or identity[1:] != [KERNEL, BOOT]:
            raise RuntimeError("unexpected boot identity")
        report["boot_id"] = identity[0]
        health = json.loads(step("health", "/usr/local/bin/lynx-status --assert-ready"))
        minimum = 25 if health["battery"]["current_mA_signed"] > 0 else 50
        if (health["boot_id"] != identity[0] or health["issues"] or
                health["battery"]["capacity_percent"] < minimum or
                health["battery"]["temperature_mC"] >= 35000 or
                health["thermal"]["max_mC"] >= 45000):
            raise RuntimeError("health gate failed")
        step("stage_dir", f"mkdir -p {STAGE}; chmod 700 {STAGE}")
        # A separate process can reboot a wedged module probe. Never unload the
        # stock camera stack, whose teardown behavior is not yet reviewed.
        watchdog = f"{STAGE}/watchdog.sh"
        step("watchdog_script", f"cat > {watchdog}",
             b"#!/bin/sh\nsleep 90\necho camera-probe-watchdog-reboot >> /run/lynx/camera-ram/watchdog.log\nreboot -f\n")
        step("watchdog_mode", f"chmod 700 {watchdog}")
        for name, expected, directory in MODULES:
            loaded = step("loaded_" + name, f"if grep -q '^{name.replace('-', '_')} ' /proc/modules; "
                          "then echo yes; else echo no; fi")
            if loaded == "yes":
                report.setdefault("already_loaded", []).append(name)
            else:
                data = (directory / (name + ".ko")).read_bytes()
                if hashlib.sha256(data).hexdigest() != expected:
                    raise RuntimeError("stock checksum mismatch: " + name)
                magic = subprocess.run(["modinfo", "-F", "vermagic",
                                        str(directory / (name + ".ko"))],
                                       capture_output=True, text=True, check=True).stdout.strip()
                if not magic.startswith(KERNEL + " "):
                    raise RuntimeError("kernel ABI mismatch: " + name)
                remote = f"{STAGE}/{name}.ko"
                step("stage_" + name, f"cat > {remote}", data, timeout=40)
                if step("hash_" + name, f"sha256sum {remote} | cut -c1-64") != expected:
                    raise RuntimeError("transfer checksum mismatch: " + name)
                pid = step("arm_" + name, f"setsid {watchdog} </dev/null "
                           f">>{STAGE}/watchdog.log 2>&1 & echo $!")
                report["attempting"] = name
                report["watchdog_pid"] = pid
                save()
                try:
                    step("load_" + name, f"/bin/busybox timeout 20 /sbin/insmod {remote}",
                         timeout=28)
                    report.setdefault("loaded", []).append(name)
                    save()
                    step("health_" + name,
                         f"set -eu; grep -q '^{name.replace('-', '_')} ' /proc/modules; "
                         "/usr/local/bin/lynx-status --assert-ready >/dev/null", timeout=15)
                finally:
                    step("disarm_" + name, f"kill {pid} 2>/dev/null || true")
                    report.pop("watchdog_pid", None)
            if name == args.through:
                break
        report["nodes"] = step("nodes", "find /dev -maxdepth 1 "
                               "\\( -name 'video*' -o -name 'media*' -o "
                               "-name 'v4l-subdev*' -o -name 'camera*' \\) | sort")
        report["dmesg"] = step("dmesg", "dmesg | grep -Ei 'ccu|imgsensor|camera|v4l2' | tail -60")[-6000:]
        report["state"] = "module-stage-complete-no-capture"
    except Exception as exc:
        report.update(state="failed-leave-loaded-modules-alone", error=str(exc))
    save()
    print(json.dumps({"state": report["state"], "receipt": str(out / "result.json"),
                      "error": report.get("error")}))
    if report["state"] != "module-stage-complete-no-capture":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
