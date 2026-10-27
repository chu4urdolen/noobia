#!/usr/bin/env python3
"""RAM-only V50 sound-card probe using the reviewed MT6338 deferral fix."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from lynx_wifi_v19_contact import ssh_command
import trial_v50_audio_modules as old


ROOT = Path(__file__).resolve().parent.parent
PATCH = ROOT / "linux-port/patches/mt6338-probe-defer.patch"
FIXED = ROOT / "linux-port/artifacts/audio-codec-fix/snd-soc-mt6338.ko"
FIXED_SHA = "d9f93f42c19fd75ae803be3726aa961c9be52a7c1960924cc6f2db82248e688f"
PATCH_SHA = "216e38ff1fb5f65beed8c74124688003e8c8c78713d18fe15f2c2975caeaab91"
KERNEL = old.KERNEL
INIT = old.INIT_SHA
BOOT = "6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59"


def ssh(command, *, data=None, port=2222, timeout=25):
    argv = ssh_command("192.168.100.107", command)
    argv[-2:-2] = ["-p", str(port)]
    return subprocess.run(argv, input=data, capture_output=True, timeout=timeout)


def main():
    os.umask(0o077)
    out = ROOT / "logs" / f"v50-audio-card-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "starting", "boot_partition_writes": False,
              "persistent_phone_writes": False, "playback_attempted": False,
              "loaded_new": [], "steps": []}

    def step(label, command, *, data=None, port=2222, timeout=25):
        result = ssh(command, data=data, port=port, timeout=timeout)
        (out / f"{label}.stdout").write_bytes(result.stdout)
        (out / f"{label}.stderr").write_bytes(result.stderr)
        report["steps"].append({"name": label, "exit": result.returncode})
        if result.returncode:
            raise RuntimeError(f"{label} failed; inspect saved streams")
        return result.stdout.decode(errors="replace").strip()

    try:
        if hashlib.sha256(PATCH.read_bytes()).hexdigest() != PATCH_SHA or \
           hashlib.sha256(FIXED.read_bytes()).hexdigest() != FIXED_SHA:
            raise RuntimeError("reviewed codec patch or binary changed")
        stock = old.STOCK / "wifi-reference/vendor-dlkm-unpacked/lib/modules/snd-soc-mt6338.ko"
        def versions(path):
            return subprocess.run(["modprobe", "--dump-modversions", str(path)],
                                  check=True, capture_output=True,
                                  text=True).stdout.splitlines()
        if set(versions(FIXED)) != set(versions(stock)):
            raise RuntimeError("codec imported symbol CRCs differ from stock")
        vm = subprocess.run(["modinfo", "-F", "vermagic", str(FIXED)],
                            check=True, capture_output=True, text=True).stdout.strip()
        if not vm.startswith(KERNEL + " "):
            raise RuntimeError("codec kernel ABI mismatch")
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
        step("providers", "set -eu; rc-service lynx-display status; "
             "test -e /sys/bus/nvmem/devices/mt6338-efuse0; "
             "grep -q '^mt6338_core ' /proc/modules; "
             "grep -q '^mt6338_auxadc ' /proc/modules; "
             "grep -q '^nvmem_mt6338_efuse ' /proc/modules; "
             "grep -q '^--- no soundcards ---' /proc/asound/cards")
        loaded = set(step("loaded_before", "cut -d' ' -f1 /proc/modules").splitlines())
        old.TARGETS = ("adsp-v2", "snd-soc-tfa98xx", "mt6983-mt6338",
                       "mtk-btcvsd", "mtk-soc-offload-common")
        plan = old.module_plan()
        if len(plan) > 80:
            raise RuntimeError("audio dependency plan unexpectedly large")
        report["module_plan"] = [{"name": name, "stock_sha256": digest}
                                 for name, _, digest, _ in plan]
        step("directory", "mkdir -p /run/lynx/audio-v50")
        for name, path, digest, data in plan:
            if name in loaded:
                continue
            if name == "snd_soc_mt6338":
                path, data, digest = FIXED, FIXED.read_bytes(), FIXED_SHA
            remote = f"/run/lynx/audio-v50/{path.name}"
            step(name + "_stage", f"set -eu; test ! -e {remote}; cat > {remote}",
                 data=data, timeout=50)
            step(name + "_verify", f'test "$(sha256sum {remote} | cut -c1-64)" = "{digest}"')
            step(name + "_load", f"/bin/busybox timeout 20 /sbin/insmod {remote}", timeout=28)
            report["loaded_new"].append(name)
            step(name + "_after", f"set -eu; grep -q '^{name} ' /proc/modules; "
                 "/usr/local/bin/lynx-status --assert-ready >/dev/null")
            loaded.add(name)
        report["cards"] = step("cards", "cat /proc/asound/cards; ls -l /dev/snd; "
                               "dmesg | grep -Ei 'mt6338|tfa98|sound|audio|snd' | tail -n 120")
        report["state"] = "sound-card-probed-no-playback"
    except Exception as exc:
        report.update(state="stopped-or-incomplete", error=str(exc))
    report["finished_ns"] = time.time_ns()
    receipt = out / "result.json"
    receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"], "result": str(receipt)}))
    if report["state"] != "sound-card-probed-no-playback":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
