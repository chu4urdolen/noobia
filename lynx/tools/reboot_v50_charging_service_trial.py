#!/usr/bin/env python3
"""Enable the verified charging service, then request one guarded V50 reboot."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import time

from trial_v50_tcpc_mt6375 import ROOT, KERNEL, INIT_SHA, ssh


IMAGE = ROOT / "linux-port/artifacts/static-noobia-ip-v50-offline/nord3-static-noobia-ip-v50-untested.img"
IMAGE_SHA = "6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reboot", action="store_true", help="enable and reboot once")
    args = parser.parse_args()
    os.umask(0o077)
    out = ROOT / "logs" / f"v50-charging-service-reboot-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "starting", "reboot_requested": args.reboot,
              "boot_partition_writes": False, "steps": []}

    def step(name, command, port=2222, timeout=20, accept_disconnect=False):
        result = ssh(command, port=port, timeout=timeout)
        (out / f"{name}.stdout").write_bytes(result.stdout)
        (out / f"{name}.stderr").write_bytes(result.stderr)
        report["steps"].append({"name": name, "exit": result.returncode})
        if result.returncode and not accept_disconnect:
            raise RuntimeError(f"{name} failed; inspect saved streams")
        return result.stdout.decode(errors="replace")

    try:
        if hashlib.sha256(IMAGE.read_bytes()).hexdigest() != IMAGE_SHA:
            raise RuntimeError("V50 boot_a rollback image missing or changed")
        identity = step("identity", "cat /proc/sys/kernel/random/boot_id; "
                        "uname -r; sha256sum /init | cut -c1-64; "
                        "grep 'LYNX_STATIC_NOOBIA_IP' /run/lynx/boot.log | tail -1",
                        port=22).splitlines()
        if (len(identity) != 4 or identity[1] != KERNEL or identity[2] != INIT_SHA or
                "address=192.168.100.107" not in identity[3]):
            raise RuntimeError("V50 identity mismatch")
        report["old_boot_id"] = identity[0]
        health = json.loads(step("health", "/usr/local/bin/lynx-status --assert-ready"))
        if (health["boot_id"] != identity[0] or
                health["battery"]["capacity_percent"] < 50 or
                health["battery"]["temperature_mC"] >= 35000 or
                health["thermal"]["max_mC"] >= 45000):
            raise RuntimeError("battery, boot, or thermal preflight failed")
        report["battery_percent"] = health["battery"]["capacity_percent"]
        step("service_preflight", "set -eu; "
             "/usr/local/bin/lynx-charging-stack --status; "
             "/sbin/rc-service lynx-charging-stack status; "
             "p=/sys/class/power_supply/11e01000.i2c:mt6375@34:chg; "
             "test \"$(cat \"$p/online\")\" = 2; "
             "grep -q '\\[DCP\\]' \"$p/usb_type\"; "
             "test -z \"$(find /etc/runlevels -type l -name lynx-charging-stack -print -quit)\"")
        step("shutdown_dry_run", "/sbin/openrc-shutdown -D -r now")
        if not args.reboot:
            report["state"] = "checked-no-change"
        else:
            step("enable", "/sbin/rc-update add lynx-charging-stack default")
            step("enabled_proof", "test -L /etc/runlevels/default/lynx-charging-stack")
            step("reboot_request", "/sbin/openrc-shutdown -r now",
                 timeout=12, accept_disconnect=True)
            report["state"] = "reboot-requested-await-new-boot"
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
