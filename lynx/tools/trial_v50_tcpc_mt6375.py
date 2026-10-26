#!/usr/bin/env python3
"""Guarded V50 RAM-only probe of the stock MT6375 Type-C controller module."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "linux-port/artifacts/stock-cph2493-August-eu-ota/vendor-ramdisk-unpacked/lib/modules/tcpc_mt6375.ko"
SHA = "91f06878fc510103c0d22c0587297321d24833ac1ccddfe99885247e300e4e5e"
IP = "192.168.100.107"
KERNEL = "5.10.149-android12-9-o-g311738fbb5a8"
INIT_SHA = "b560f233f5ecf838b5e948d0cd3685b676a84f3097adb00d2c8bfa6e5446ab1f"
DEVICE = "/sys/bus/platform/devices/11e01000.i2c:mt6375@34:tcpc"
REMOTE = "/run/lynx/tcpc-test/tcpc_mt6375.ko"
CHARGER = "/sys/class/power_supply/11e01000.i2c:mt6375@34:chg"


def ssh(command, payload=None, port=2222, timeout=20):
    argv = ssh_command(IP, command)
    argv[-2:-2] = ["-p", str(port)]
    return subprocess.run(argv, input=payload, capture_output=True, timeout=timeout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="load one module into RAM")
    args = parser.parse_args()
    os.umask(0o077)
    out = ROOT / "logs" / f"v50-tcpc-trial-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "starting", "apply": args.apply,
              "boot_partition_writes": False, "persistent_phone_files": False,
              "module": "tcpc_mt6375.ko", "module_sha256": SHA,
              "steps": []}

    def step(name, command, payload=None, port=2222, timeout=20):
        result = ssh(command, payload, port, timeout)
        (out / f"{name}.stdout").write_bytes(result.stdout)
        (out / f"{name}.stderr").write_bytes(result.stderr)
        report["steps"].append({"name": name, "exit": result.returncode})
        if result.returncode:
            raise RuntimeError(f"{name} failed; inspect saved streams")
        return result.stdout.decode(errors="replace")

    try:
        data = SOURCE.read_bytes()
        if hashlib.sha256(data).hexdigest() != SHA:
            raise RuntimeError("stock TCPC module hash mismatch")
        vermagic = subprocess.run(["modinfo", "-F", "vermagic", str(SOURCE)],
                                 capture_output=True, text=True, check=True).stdout
        if not vermagic.startswith(KERNEL + " "):
            raise RuntimeError("stock TCPC module ABI mismatch")
        identity = step("identity", "cat /proc/sys/kernel/random/boot_id; "
                        "uname -r; sha256sum /init | cut -c1-64; "
                        "grep 'LYNX_STATIC_NOOBIA_IP' /run/lynx/boot.log | tail -1",
                        port=22).splitlines()
        if (len(identity) != 4 or identity[1] != KERNEL or
                identity[2] != INIT_SHA or
                "address=192.168.100.107" not in identity[3]):
            raise RuntimeError("V50 boot identity or static address proof missing")
        report["boot_id"] = identity[0]
        health = json.loads(step("health_before", "/usr/local/bin/lynx-status --assert-ready"))
        report["battery_percent_before"] = health["battery"]["capacity_percent"]
        report["battery_temperature_mC_before"] = health["battery"]["temperature_mC"]
        if (health["boot_id"] != identity[0] or
                health["battery"]["capacity_percent"] < 22 or
                health["battery"]["temperature_mC"] >= 35000 or
                health["thermal"]["max_mC"] >= 45000):
            raise RuntimeError("boot, battery, or thermal preflight failed")
        before = step("tcpc_preflight", "set -eu; "
                      "grep -q '^tcpc_class ' /proc/modules; "
                      "grep -q '^pd_dbg_info ' /proc/modules; "
                      "! grep -q '^tcpc_mt6375 ' /proc/modules; "
                      f"test -d '{DEVICE}'; test ! -L '{DEVICE}/driver'; "
                      f"cat '{CHARGER}/online'; cat '{CHARGER}/status'").splitlines()
        report["charger_before"] = before
        if len(before) != 2 or not before[0].isdigit():
            raise RuntimeError("charger state unavailable")
        if int(before[0]) > 0:
            report["state"] = "charging-already-online-no-change"
        elif not args.apply:
            report["state"] = "checked-no-change"
        else:
            step("stage", f"mkdir -p /run/lynx/tcpc-test; cat > '{REMOTE}'",
                 payload=data, timeout=40)
            step("remote_hash", f'test "$(sha256sum {REMOTE} | cut -c1-64)" = "{SHA}"')
            step("insmod_once", f"/bin/busybox timeout 15 /sbin/insmod '{REMOTE}'",
                 timeout=22)
            step("module_bound", "set -eu; grep -q '^tcpc_mt6375 ' /proc/modules; "
                 f"test -L '{DEVICE}/driver'; cat '{CHARGER}/online'; "
                 f"cat '{CHARGER}/status'")
            time.sleep(10)
            after = step("after", "/usr/local/bin/lynx-status --assert-ready; "
                         f"cat '{CHARGER}/online'; cat '{CHARGER}/status'").splitlines()
            report["health_after"] = json.loads(after[0])
            report["charger_after"] = after[1:3]
            step("dmesg_after", "dmesg", timeout=25)
            report["state"] = "module-loaded-same-boot"
    except Exception as exc:
        report.update(state="stopped-or-incomplete", error=str(exc))
    report["finished_ns"] = time.time_ns()
    path = out / "result.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"], "result": str(path)}))
    if report["state"] == "stopped-or-incomplete":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
