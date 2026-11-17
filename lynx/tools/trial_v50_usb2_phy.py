#!/usr/bin/env python3
"""Load the matching stock USB PHY once in V50 RAM, with charger evidence."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from trial_v50_tcpc_mt6375 import ROOT, KERNEL, INIT_SHA, CHARGER, ssh


SOURCE = ROOT / "linux-port/artifacts/stock-cph2493-August-eu-ota/vendor-ramdisk-unpacked/lib/modules/phy-mtk-xsphy.ko"
SHA = "d83486fe2a36bc122c107117851dfbc790f87440cd301720762be99299468f69"
REMOTE = "/run/lynx/charging-test/phy-mtk-xsphy.ko"
PHY_DEVICE = "/sys/bus/platform/devices/11e43000.usb-phy0"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="load one stock module into RAM")
    args = parser.parse_args()
    os.umask(0o077)
    out = ROOT / "logs" / f"v50-usb2-phy-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "starting", "apply": args.apply, "module_sha256": SHA,
              "boot_partition_writes": False, "persistent_phone_files": False,
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
            raise RuntimeError("stock USB PHY module hash mismatch")
        vermagic = subprocess.run(["modinfo", "-F", "vermagic", str(SOURCE)],
                                 capture_output=True, text=True, check=True).stdout
        if not vermagic.startswith(KERNEL + " "):
            raise RuntimeError("USB PHY module ABI mismatch")
        depends = subprocess.run(["modinfo", "-F", "depends", str(SOURCE)],
                                 capture_output=True, text=True, check=True).stdout.strip()
        if depends:
            raise RuntimeError(f"unexpected USB PHY module dependencies: {depends}")
        identity = step("identity", "cat /proc/sys/kernel/random/boot_id; "
                        "uname -r; sha256sum /init | cut -c1-64; "
                        "grep 'LYNX_STATIC_NOOBIA_IP' /run/lynx/boot.log | tail -1",
                        port=22).splitlines()
        if (len(identity) != 4 or identity[1] != KERNEL or identity[2] != INIT_SHA or
                "address=192.168.100.107" not in identity[3]):
            raise RuntimeError("V50 identity or static address proof missing")
        report["boot_id"] = identity[0]
        health = json.loads(step("health_before", "/usr/local/bin/lynx-status --assert-ready"))
        report["battery_before"] = health["battery"]["capacity_percent"]
        if (health["boot_id"] != identity[0] or
                health["battery"]["capacity_percent"] < 25 or
                health["battery"]["temperature_mC"] >= 35000 or
                health["thermal"]["max_mC"] >= 45000):
            raise RuntimeError("boot, battery, or thermal preflight failed")
        pre = step("preflight", "set -eu; "
                   "! grep -q '^phy_mtk_xsphy ' /proc/modules; "
                   f"test -d '{PHY_DEVICE}'; test ! -L '{PHY_DEVICE}/driver'; "
                   "grep -q '^tcpc_mt6375 ' /proc/modules; "
                   "grep -q '^mtk_chg_type_det ' /proc/modules; "
                   f"cat '{CHARGER}/online'; cat '{CHARGER}/status'").splitlines()
        report["charger_before"] = pre
        if len(pre) != 2 or pre[0] != "2" or pre[1] != "Charging":
            raise RuntimeError("Hama Type-C charger attach is not present")
        if not args.apply:
            report["state"] = "checked-no-change"
        else:
            step("stage", f"mkdir -p /run/lynx/charging-test; cat > '{REMOTE}'",
                 payload=data, timeout=40)
            step("remote_hash", f'test "$(sha256sum {REMOTE} | cut -c1-64)" = "{SHA}"')
            step("insmod_once", f"/bin/busybox timeout 15 /sbin/insmod '{REMOTE}'",
                 timeout=22)
            step("module_bound", "set -eu; "
                 "grep -q '^phy_mtk_xsphy ' /proc/modules; "
                 f"test -L '{PHY_DEVICE}/driver'; "
                 "test -d /sys/class/phy")
            after = step("health_after", "/usr/local/bin/lynx-status --assert-ready")
            report["health_after"] = json.loads(after)
            report["charger_after"] = step("charger_after",
                f"cat '{CHARGER}/online'; cat '{CHARGER}/status'").splitlines()
            step("dmesg_after", "dmesg | tail -120")
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
