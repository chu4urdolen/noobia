#!/usr/bin/env python3
"""Load matching stock Nord 3 audio modules into V50 RAM one at a time."""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
STOCK = ROOT / "linux-port/artifacts/stock-cph2493-August-eu-ota"
ROOTS = (STOCK / "vendor-ramdisk-unpacked/lib/modules",
         STOCK / "wifi-reference/vendor-dlkm-unpacked/lib/modules")
KERNEL = "5.10.149-android12-9-o-g311738fbb5a8"
INIT_SHA = "b560f233f5ecf838b5e948d0cd3685b676a84f3097adb00d2c8bfa6e5446ab1f"
IP = "192.168.100.107"
TARGETS = ("mt6338-core", "mt6338-auxadc", "nvmem-mt6338-efuse",
           "adsp-v2", "snd-soc-tfa98xx", "mtk-btcvsd", "mt6983-mt6338",
           "mtk-soc-offload-common")


def ssh(command, payload=None, *, port=2222, timeout=25):
    argv = ssh_command(IP, command)
    argv[-2:-2] = ["-p", str(port)]
    return subprocess.run(argv, input=payload, capture_output=True, timeout=timeout)


def module_plan():
    files = {path.stem.replace("-", "_"): path
             for root in ROOTS for path in root.glob("*.ko")}
    seen, plan = set(), []

    def visit(name):
        name = name.replace("-", "_")
        if not re.fullmatch(r"[A-Za-z0-9_]+", name):
            raise RuntimeError("unexpected module dependency name")
        if name in seen:
            return
        seen.add(name)
        path = files.get(name)
        if path is None:
            raise RuntimeError(f"missing stock dependency {name}")
        vermagic = subprocess.run(["modinfo", "-F", "vermagic", str(path)],
                                 capture_output=True, text=True, check=True).stdout.strip()
        if not vermagic.startswith(KERNEL + " "):
            raise RuntimeError(f"{name}: kernel ABI mismatch")
        deps = subprocess.run(["modinfo", "-F", "depends", str(path)],
                              capture_output=True, text=True, check=True).stdout.strip()
        for dep in filter(None, deps.split(",")):
            visit(dep)
        data = path.read_bytes()
        plan.append((name, path, hashlib.sha256(data).hexdigest(), data))

    for target in TARGETS:
        visit(target)
    return plan


def main():
    os.umask(0o077)
    out = ROOT / "logs" / f"v50-audio-module-trial-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "starting", "boot_partition_writes": False,
              "pcm_playback_attempted": False, "firmware_writes": False,
              "steps": [], "loaded_new": []}

    def step(label, command, payload=None, *, port=2222, timeout=25):
        result = ssh(command, payload, port=port, timeout=timeout)
        (out / f"{label}.stdout").write_bytes(result.stdout)
        (out / f"{label}.stderr").write_bytes(result.stderr)
        report["steps"].append({"name": label, "exit": result.returncode})
        if result.returncode:
            raise RuntimeError(f"{label} failed; inspect saved streams")
        return result.stdout.decode(errors="replace").strip()

    try:
        plan = module_plan()
        report["module_plan"] = [{"name": name, "path": str(path), "sha256": digest}
                                 for name, path, digest, _ in plan]
        identity = step("identity", "cat /proc/sys/kernel/random/boot_id; "
                        "uname -r; sha256sum /init | cut -c1-64", port=22).splitlines()
        if len(identity) != 3 or identity[1:] != [KERNEL, INIT_SHA]:
            raise RuntimeError("unexpected V50 rescue or kernel identity")
        boot_id = identity[0]
        report["boot_id"] = boot_id
        health = json.loads(step("health", "/usr/local/bin/lynx-status --assert-ready"))
        if health["boot_id"] != boot_id or health["battery"]["capacity_percent"] < 50 or \
           health["battery"]["temperature_mC"] >= 30000 or \
           health["thermal"]["max_mC"] >= 45000:
            raise RuntimeError("audio trial battery or thermal guard failed")
        step("display_touch", "set -eu; "
             "test \"$(cat /sys/class/input/input0/name)\" = touchpanel; "
             "test -s /run/lynx/status-touch.pid; "
             "kill -0 $(cat /run/lynx/status-touch.pid); "
             "test -e /proc/asound/cards; "
             "grep -q '^--- no soundcards ---' /proc/asound/cards")
        loaded = set(step("loaded_before", "cut -d' ' -f1 /proc/modules").splitlines())
        for name, path, digest, data in plan:
            if name in loaded:
                continue
            remote = f"/run/lynx/audio-test/{path.name}"
            step(name + "_preflight", "set -eu; "
                 f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{boot_id}"; '
                 f"test ! -e /sys/module/{name}; test ! -e {remote}; "
                 "/usr/local/bin/lynx-status --assert-ready >/dev/null")
            step(name + "_stage", f"mkdir -p /run/lynx/audio-test; cat > {remote}",
                 payload=data, timeout=45)
            step(name + "_verify", f'test "$(sha256sum {remote} | cut -c1-64)" = "{digest}"')
            step(name + "_load", f"/bin/busybox timeout 20 /sbin/insmod {remote}",
                 timeout=30)
            step(name + "_after", "set -eu; "
                 f"grep -q '^{name} ' /proc/modules; "
                 "/usr/local/bin/lynx-status --assert-ready >/dev/null")
            loaded.add(name)
            report["loaded_new"].append(name)
        report["cards"] = step("cards", "cat /proc/asound/cards; ls -l /dev/snd")
        report["state"] = "audio-modules-loaded-no-playback"
    except Exception as exc:
        report.update(state="stopped-or-incomplete", error=str(exc))
        try:
            step("after_failure", "cat /proc/asound/cards; "
                 "/usr/local/bin/lynx-status --assert-ready; dmesg | tail -100", timeout=20)
        except Exception:
            pass
    report["finished_ns"] = time.time_ns()
    path = out / "result.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"], "result": str(path)}))
    if report["state"] != "audio-modules-loaded-no-playback":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
