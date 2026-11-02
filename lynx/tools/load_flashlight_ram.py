#!/usr/bin/env python3
"""Load Lynx's matching flashlight modules in RAM; never unload them."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
STOCK = ROOT / "linux-port/artifacts/stock-cph2493-August-eu-ota/wifi-reference/vendor-dlkm-unpacked/lib/modules"
MODULES = (
    ("mtk_battery_oc_throttling", "2285905a04532af8eaf2a04ad436eb14b4c8a7fc2bdbeaed3e5f647005b0cdf3"),
    ("flashlight", "58dbf6edb80115078739a3b008ef73a2bad734f9c4812a1f34b8e28ae36bb915"),
    ("lm3642_22823", "96dc429c39453dbd0ba469069655bfafc43e329cc3216d912bb080e87b7bef67"),
)
KERNEL = "5.10.149-android12-9-o-g311738fbb5a8"
BOOT = "c047455271828cf9bfa90984eea121d8ede8754f6297fc06f33f1e99fb23c75e"
STAGE = "/run/lynx/flashlight-ram"


def main():
    os.umask(0o077)
    out = ROOT / "logs" / f"flashlight-ram-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "starting", "boot_partition_writes": False,
              "led_actuation_requested": False, "modules_unloaded": False, "steps": []}

    def save():
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")

    def step(name, command, data=None, timeout=20):
        args = ssh_command("192.168.100.107", command)
        args[-2:-2] = ["-p", "2222"]
        result = subprocess.run(args, input=data, capture_output=True, timeout=timeout)
        (out / f"{name}.stdout").write_bytes(result.stdout)
        (out / f"{name}.stderr").write_bytes(result.stderr)
        report["steps"].append({"name": name, "exit": result.returncode})
        save()
        if result.returncode:
            raise RuntimeError(f"{name} failed; see receipt")
        return result.stdout.decode(errors="replace").strip()

    try:
        identity = step("identity", "cat /proc/sys/kernel/random/boot_id; uname -r; "
                        "sha256sum /dev/sdc39 | cut -c1-64", timeout=30).splitlines()
        if len(identity) != 3 or identity[1:] != [KERNEL, BOOT]:
            raise RuntimeError("not the verified V53 boot")
        report["boot_id"] = identity[0]
        health = json.loads(step("health", "/usr/local/bin/lynx-status --assert-ready"))
        if (health["boot_id"] != identity[0] or health["issues"] or
                health["battery"]["capacity_percent"] < 50 or
                health["battery"]["temperature_mC"] >= 35000 or
                health["thermal"]["max_mC"] >= 45000):
            raise RuntimeError("health gate failed")
        step("hardware", "set -eu; test \"$(cat /sys/bus/i2c/devices/6-0063/name)\" = lm3642_22823; "
             "test ! -e /sys/bus/i2c/devices/6-0063/driver; "
             "test ! -e /dev/flashlight; "
             "grep -q '^mtk_pbm ' /proc/modules; " +
             "; ".join(f"! grep -q '^{name} ' /proc/modules" for name, _ in MODULES))
        step("stage_dir", f"mkdir -m 700 {STAGE}")
        for name, expected in MODULES:
            source = STOCK / f"{name}.ko"
            data = source.read_bytes()
            if hashlib.sha256(data).hexdigest() != expected:
                raise RuntimeError(f"stock checksum mismatch: {name}")
            magic = subprocess.run(["modinfo", "-F", "vermagic", str(source)],
                                   capture_output=True, text=True, check=True).stdout.strip()
            if not magic.startswith(KERNEL + " "):
                raise RuntimeError(f"kernel ABI mismatch: {name}")
            remote = f"{STAGE}/{name}.ko"
            step(f"stage_{name}", f"cat > {remote}", data, timeout=40)
            if step(f"hash_{name}", f"sha256sum {remote} | cut -c1-64") != expected:
                raise RuntimeError(f"transfer hash mismatch: {name}")
            report["attempting"] = name
            save()
            step(f"load_{name}", f"/bin/busybox timeout 15 /sbin/insmod {remote}", timeout=22)
            report.setdefault("loaded", []).append(name)
            save()
            step(f"health_{name}", f"set -eu; grep -q '^{name} ' /proc/modules; "
                 "/usr/local/bin/lynx-status --assert-ready >/dev/null")
        binding = step("binding", "set -eu; test -L /sys/bus/i2c/devices/6-0063/driver; "
                       "test -c /dev/flashlight; "
                       "cat /sys/class/flashlight/flashlight/flashlight_torch 2>/dev/null || true; "
                       "dmesg | grep -Ei 'lm3642_22823|flashlight_core|flashlight' | tail -35")
        report["binding_log"] = binding[-4000:]
        report["state"] = "bound-in-ram-no-led-actuation"
    except Exception as exc:
        report.update(state="failed-leave-loaded-modules-alone", error=str(exc))
    save()
    print(json.dumps({"state": report["state"], "receipt": str(out / "result.json"),
                      "error": report.get("error")}))
    if report["state"] != "bound-in-ram-no-led-actuation":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
