#!/usr/bin/env python3
"""Stage exact stock Bluetooth modules in V50 RAM; never load or power radios."""

import hashlib
import json
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
STOCK = ROOT / "linux-port/artifacts/stock-cph2493-August-eu-ota/wifi-reference/vendor-dlkm-unpacked/lib/modules"
V50_SHA = "6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59"
KERNEL = "5.10.149-android12-9-o-g311738fbb5a8"
MODULES = {
    "btif_drv.ko": "f81ec909db5e986b2a8e23fa1c34f3f3a027a07e2da5335fc3917b8bf9615d51",
    "bt_drv_6983.ko": "f6c99218edc8e903b2ccbaac7f9e7176cd11b6129350ff738fb64d1b9ade5296",
}
STAGE = "/run/lynx-bt-ram"


def phone(command, data=None):
    argv = ssh_command("192.168.100.107", command)
    argv[-2:-2] = ["-p", "2222"]
    return subprocess.run(argv, input=data, capture_output=True, timeout=30)


def main():
    out = ROOT / "logs" / f"v50-bt-ram-stage-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "preflight", "boot_partition_writes": False,
              "persistent_phone_writes": False, "modules_loaded": False,
              "wifi_changed": False, "files": []}

    def save():
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")

    save()
    try:
        cmd = ("set -eu; cat /proc/sys/kernel/random/boot_id; uname -r; "
               "sha256sum /dev/sdc39 | cut -c1-64; "
               "test -c /dev/wmtWifi; test ! -e /dev/stpbt; "
               "test ! -d /sys/module/btif_drv; test ! -d /sys/module/bt_drv_6983; "
               "/usr/local/bin/lynx-status --assert-ready")
        checked = phone(cmd)
        if checked.returncode:
            raise RuntimeError("V50 identity or health preflight failed")
        lines = checked.stdout.decode().splitlines()
        if len(lines) != 4 or lines[1] != KERNEL or lines[2] != V50_SHA:
            raise RuntimeError("V50 kernel or boot image mismatch")
        health = json.loads(lines[3])
        if health["issues"] or health["battery"]["capacity_percent"] < 25:
            raise RuntimeError("V50 battery or health guard failed")
        report["boot_id"] = lines[0]
        report["battery_percent"] = health["battery"]["capacity_percent"]
        created = phone(f"set -eu; test ! -e {STAGE}; mkdir -m 700 {STAGE}")
        if created.returncode:
            raise RuntimeError("RAM stage already exists or cannot be created")
        for name, expected in MODULES.items():
            data = (STOCK / name).read_bytes()
            if hashlib.sha256(data).hexdigest() != expected:
                raise RuntimeError("matching stock module differs: " + name)
            remote = f"{STAGE}/{name}"
            cmd = (f"set -eu; umask 077; cat > {remote}.part; "
                   f'test "$(sha256sum {remote}.part | cut -c1-64)" = {expected}; '
                   f"mv {remote}.part {remote}; test -f {remote}")
            result = phone(cmd, data)
            if result.returncode:
                raise RuntimeError("RAM stage failed: " + name)
            report["files"].append({"name": name, "sha256": expected,
                                    "bytes": len(data), "remote": remote})
            save()
        after = phone("set -eu; cat /proc/sys/kernel/random/boot_id; "
                      "test ! -d /sys/module/btif_drv; "
                      "test ! -d /sys/module/bt_drv_6983; "
                      "test ! -e /dev/stpbt; "
                      "/usr/local/bin/lynx-status --assert-ready")
        if after.returncode or after.stdout.decode().splitlines()[0] != report["boot_id"]:
            raise RuntimeError("V50 changed during RAM stage")
        report["state"] = "staged-in-ram-not-loaded"
    except Exception as exc:
        report.update(state="failed", error=str(exc))
    save()
    print(json.dumps({"state": report["state"], "receipt": str(out / "result.json"),
                      "modules": len(report["files"]), "error": report.get("error")}))
    if report["state"] != "staged-in-ram-not-loaded":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
