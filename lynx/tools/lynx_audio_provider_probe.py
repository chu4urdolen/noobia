#!/usr/bin/env python3
"""Load only the previously tolerated MT6338 providers into V50 RAM."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
STOCK = ROOT / "linux-port/artifacts/stock-cph2493-August-eu-ota"
KERNEL = "5.10.149-android12-9-o-g311738fbb5a8"
INIT = "b560f233f5ecf838b5e948d0cd3685b676a84f3097adb00d2c8bfa6e5446ab1f"
BOOT = "6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59"
MODULES = (
    ("mt6338_core", STOCK / "vendor-ramdisk-unpacked/lib/modules/mt6338-core.ko"),
    ("mt6338_auxadc", STOCK / "vendor-ramdisk-unpacked/lib/modules/mt6338-auxadc.ko"),
    ("nvmem_mt6338_efuse", STOCK / "wifi-reference/vendor-dlkm-unpacked/lib/modules/nvmem-mt6338-efuse.ko"),
)


def main():
    os.umask(0o077)
    out = ROOT / "logs" / f"v50-audio-provider-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "starting", "boot_partition_writes": False,
              "persistent_phone_writes": False, "loaded": [], "steps": []}

    def step(label, command, *, data=None, port=2222, timeout=25):
        argv = ssh_command("192.168.100.107", command)
        argv[-2:-2] = ["-p", str(port)]
        result = subprocess.run(argv, input=data, capture_output=True, timeout=timeout)
        (out / f"{label}.stdout").write_bytes(result.stdout)
        (out / f"{label}.stderr").write_bytes(result.stderr)
        report["steps"].append({"name": label, "exit": result.returncode})
        if result.returncode:
            raise RuntimeError(f"{label} failed; inspect saved streams")
        return result.stdout.decode(errors="replace").strip()

    try:
        identity = step("identity", "cat /proc/sys/kernel/random/boot_id; uname -r; "
                        "sha256sum /init | cut -c1-64; sha256sum /dev/sdc39 | cut -c1-64",
                        port=22).splitlines()
        if len(identity) != 4 or identity[1:] != [KERNEL, INIT, BOOT]:
            raise RuntimeError("V50 boot identity changed")
        report["boot_id"] = identity[0]
        health = json.loads(step("health", "/usr/local/bin/lynx-status --assert-ready"))
        if health["boot_id"] != identity[0] or \
           health["battery"]["capacity_percent"] < 50 or \
           health["battery"]["temperature_mC"] >= 30000 or \
           health["thermal"]["max_mC"] >= 45000:
            raise RuntimeError("battery or thermal preflight failed")
        step("display", "rc-service lynx-display status; "
             "grep -q '^--- no soundcards ---' /proc/asound/cards; "
             "test ! -d /sys/module/mt6338_core; "
             "test ! -d /sys/module/mt6338_auxadc; "
             "test ! -d /sys/module/nvmem_mt6338_efuse")
        step("baseline", "dmesg | tail -n 80")
        step("directory", "mkdir -p /run/lynx/audio-v50")
        for name, path in MODULES:
            data = path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            vermagic = subprocess.run(["modinfo", "-F", "vermagic", str(path)],
                                     check=True, capture_output=True,
                                     text=True).stdout.strip()
            if not vermagic.startswith(KERNEL + " "):
                raise RuntimeError(f"{name}: stock kernel mismatch")
            remote = f"/run/lynx/audio-v50/{path.name}"
            step(name + "_stage", f"set -eu; test ! -e {remote}; cat > {remote}",
                 data=data, timeout=45)
            step(name + "_verify", f'test "$(sha256sum {remote} | cut -c1-64)" = "{digest}"')
            step(name + "_load", f"/bin/busybox timeout 20 /sbin/insmod {remote}", timeout=28)
            report["loaded"].append(name)
            step(name + "_after", f"set -eu; grep -q '^{name} ' /proc/modules; "
                 "/usr/local/bin/lynx-status --assert-ready >/dev/null")
        report["providers"] = step("providers", "find /sys/bus/nvmem/devices -mindepth 1 -maxdepth 1; "
                                   "find /sys/bus/iio/devices -mindepth 1 -maxdepth 1 | head -20; "
                                   "cat /proc/asound/cards; dmesg | tail -n 100")
        report["state"] = "providers-loaded-no-playback"
    except Exception as exc:
        report.update(state="stopped-or-incomplete", error=str(exc))
    report["finished_ns"] = time.time_ns()
    receipt = out / "result.json"
    receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"], "result": str(receipt)}))
    if report["state"] != "providers-loaded-no-playback":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
