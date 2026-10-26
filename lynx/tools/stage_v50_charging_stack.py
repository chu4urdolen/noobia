#!/usr/bin/env python3
"""Stage the proven V50 charging modules and OpenRC service, disabled."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from trial_v50_tcpc_mt6375 import ROOT, KERNEL, INIT_SHA, ssh


MODULE_DIR = ROOT / "linux-port/artifacts/stock-cph2493-August-eu-ota/vendor-ramdisk-unpacked/lib/modules"
MODULES = (
    ("phy-mtk-xsphy", "d83486fe2a36bc122c107117851dfbc790f87440cd301720762be99299468f69"),
    ("tcpc_mt6375", "91f06878fc510103c0d22c0587297321d24833ac1ccddfe99885247e300e4e5e"),
    ("mtk_chg_type_det", "e5d424193c78f1d051573d06c21a76eb7d9b5df776d4175aa3313d17428f70ab"),
    ("tcpci_late_sync", "2c18ff5fa172c851599aec0a154f89b0a89c75f904262f9124674565769597f9"),
)
FILES = (
    (ROOT / "linux-port/lynx-charging-stack.sh", "/usr/local/bin/lynx-charging-stack"),
    (ROOT / "linux-port/openrc-lynx-charging-stack", "/etc/init.d/lynx-charging-stack"),
)


def main():
    os.umask(0o077)
    out = ROOT / "logs" / f"v50-charging-stack-stage-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "starting", "boot_partition_writes": False,
              "service_enabled": False, "reboot_requested": False,
              "steps": []}

    def step(name, command, payload=None, port=2222, timeout=25):
        result = ssh(command, payload, port, timeout)
        (out / f"{name}.stdout").write_bytes(result.stdout)
        (out / f"{name}.stderr").write_bytes(result.stderr)
        report["steps"].append({"name": name, "exit": result.returncode})
        if result.returncode:
            raise RuntimeError(f"{name} failed; inspect saved streams")
        return result.stdout.decode(errors="replace")

    try:
        payloads = []
        for filename, expected in MODULES:
            path = MODULE_DIR / (filename + ".ko")
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != expected:
                raise RuntimeError(f"{filename} hash mismatch")
            vermagic = subprocess.run(["modinfo", "-F", "vermagic", str(path)],
                                     capture_output=True, text=True, check=True).stdout
            if not vermagic.startswith(KERNEL + " "):
                raise RuntimeError(f"{filename} ABI mismatch")
            payloads.append((filename + ".ko", expected, data))
        for host, remote in FILES:
            data = host.read_bytes()
            if b"\r" in data:
                raise RuntimeError(f"unexpected CR in {host}")
            payloads.append((remote, hashlib.sha256(data).hexdigest(), data))
        identity = step("identity", "cat /proc/sys/kernel/random/boot_id; "
                        "uname -r; sha256sum /init | cut -c1-64; "
                        "grep 'LYNX_STATIC_NOOBIA_IP' /run/lynx/boot.log | tail -1",
                        port=22).splitlines()
        if (len(identity) != 4 or identity[1] != KERNEL or identity[2] != INIT_SHA or
                "address=192.168.100.107" not in identity[3]):
            raise RuntimeError("V50 identity mismatch")
        report["boot_id"] = identity[0]
        health = json.loads(step("health_before", "/usr/local/bin/lynx-status --assert-ready"))
        if (health["boot_id"] != identity[0] or
                health["battery"]["capacity_percent"] < 50 or
                health["battery"]["temperature_mC"] >= 35000 or
                health["thermal"]["max_mC"] >= 45000):
            raise RuntimeError("battery, boot, or thermal preflight failed")
        report["battery_percent"] = health["battery"]["capacity_percent"]
        step("preflight", "set -eu; "
             "test ! -e /etc/init.d/lynx-charging-stack; "
             "test ! -e /usr/local/bin/lynx-charging-stack; "
             "test -z \"$(find /etc/runlevels -type l -name lynx-charging-stack -print -quit)\"; "
             "for n in phy_mtk_xsphy tcpc_mt6375 mtk_chg_type_det tcpci_late_sync; do "
             "grep -q \"^$n \" /proc/modules; done; "
             "p=/sys/class/power_supply/11e01000.i2c:mt6375@34:chg; "
             "test \"$(cat \"$p/online\")\" = 2; "
             "grep -q '\\[DCP\\]' \"$p/usb_type\"")
        step("mkdir", "mkdir -p /usr/local/lib/lynx-charging/modules")
        for filename, expected, data in payloads:
            remote = (filename if filename.startswith("/") else
                      "/usr/local/lib/lynx-charging/modules/" + filename)
            tmp = remote + ".new"
            label = remote.rsplit("/", 1)[-1].replace(".", "_").replace("-", "_")
            step(label + "_write", f"cat > '{tmp}'", payload=data, timeout=45)
            step(label + "_verify", "set -eu; "
                 f'test "$(sha256sum "{tmp}" | cut -c1-64)" = "{expected}"; '
                 f"chmod {'755' if remote.startswith(('/usr/local/bin/', '/etc/init.d/')) else '644'} '{tmp}'; "
                 f"mv '{tmp}' '{remote}'")
        proof = step("idempotent_start", "/usr/local/bin/lynx-charging-stack --start")
        if proof.count("already loaded:") != 4 or "charging stack ready" not in proof:
            raise RuntimeError("idempotent start did not verify all four modules")
        step("disabled_proof", "set -eu; "
             "test -z \"$(find /etc/runlevels -type l -name lynx-charging-stack -print -quit)\"; "
             "/usr/local/bin/lynx-charging-stack --status; "
             "/usr/local/bin/lynx-status --assert-ready >/dev/null")
        report["state"] = "staged-disabled-and-idempotent"
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
