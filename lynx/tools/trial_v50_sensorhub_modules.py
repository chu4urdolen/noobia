#!/usr/bin/env python3
"""Guarded RAM-only probe of the matching Nord 3 sensorhub modules."""

import hashlib
import json
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
STOCK = ROOT / "linux-port/artifacts/stock-cph2493-August-eu-ota/wifi-reference/vendor-dlkm-unpacked/lib/modules"
MODULES = (
    ("hf_manager", "6556d801250d2f7c21d55542337df7b7f4793ecce48551603525b52d0617e677"),
    ("sensorhub", "10eede8b4673d3cc81894ed76fa7a044eec10e90b52464483848bda10d93154e"),
)
KERNEL = "5.10.149-android12-9-o-g311738fbb5a8"
INIT = "b560f233f5ecf838b5e948d0cd3685b676a84f3097adb00d2c8bfa6e5446ab1f"
BOOT = "6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59"


def ssh(command, data=None, port=2222, timeout=15):
    args = ssh_command("192.168.100.107", command)
    args[-2:-2] = ["-p", str(port)]
    return subprocess.run(args, input=data, capture_output=True, timeout=timeout)


def main():
    out = ROOT / "logs" / f"v50-sensorhub-module-trial-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "preflight", "boot_partition_writes": False,
              "persistent_phone_writes": False, "loaded": [], "steps": []}

    def save():
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")

    def step(name, command, data=None, port=2222, timeout=15):
        result = ssh(command, data, port, timeout)
        (out / f"{name}.stdout").write_bytes(result.stdout)
        (out / f"{name}.stderr").write_bytes(result.stderr)
        report["steps"].append({"name": name, "exit": result.returncode})
        save()
        if result.returncode:
            raise RuntimeError(f"{name} failed; see saved output")
        return result.stdout.decode(errors="replace")

    try:
        identity = step("identity", "cat /proc/sys/kernel/random/boot_id; "
                        "uname -r; sha256sum /init /dev/sdc39 | cut -c1-64",
                        port=22, timeout=25).splitlines()
        if len(identity) != 4 or identity[1:] != [KERNEL, INIT, BOOT]:
            raise RuntimeError("not the verified V50 boot")
        report["boot_id"] = identity[0]
        health = json.loads(step("health_before", "/usr/local/bin/lynx-status --assert-ready"))
        battery = health["battery"]
        if (health["boot_id"] != identity[0] or battery["capacity_percent"] < 50 or
            battery["temperature_mC"] >= 35000 or health["thermal"]["max_mC"] >= 40000 or
            health["root_free_mib"] < 400):
            raise RuntimeError("battery, thermal, or storage preflight failed")
        step("providers_before", "set -eu; grep -q '^scp ' /proc/modules; "
             "grep -q '^mtk_tinysys_ipi ' /proc/modules; "
             "test -L /sys/bus/platform/devices/1c400000.scp/driver; "
             "test -c /dev/scp; "
             "! grep -q '^hf_manager ' /proc/modules; "
             "! grep -q '^sensorhub ' /proc/modules; "
             "rc-service lynx-display status; rc-service lynx-audio status")
        plan = []
        for name, digest in MODULES:
            path = STOCK / f"{name}.ko"
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != digest:
                raise RuntimeError(f"stock module checksum mismatch: {name}")
            magic = subprocess.run(["modinfo", "-F", "vermagic", str(path)],
                                   capture_output=True, text=True, check=True).stdout.strip()
            if not magic.startswith(KERNEL + " "):
                raise RuntimeError(f"kernel ABI mismatch: {name}")
            plan.append((name, digest, data))
        report["plan"] = [{"name": name, "sha256": digest} for name, digest, _ in plan]
        step("directory", "mkdir -m 700 /run/lynx/sensorhub-trial")
        for name, digest, data in plan:
            remote = f"/run/lynx/sensorhub-trial/{name}.ko"
            step(name + "_stage", f"cat > {remote}", data, timeout=35)
            step(name + "_verify", f'test "$(sha256sum {remote} | cut -c1-64)" = {digest}')
            step(name + "_load", f"/bin/busybox timeout 20 /sbin/insmod {remote}", timeout=30)
            report["loaded"].append(name)
            save()
            step(name + "_after", f"set -eu; grep -q '^{name} ' /proc/modules; "
                 "/usr/local/bin/lynx-status --assert-ready >/dev/null")
        step("sensor_interfaces", "set -eu; cat /proc/modules | grep -E '^(sensorhub|hf_manager) '; "
             "find /dev -maxdepth 1 -iname '*sensor*' -o -iname '*hf*'; "
             "find /sys/bus/platform/devices -maxdepth 1 -iname '*sensor*'; "
             "dmesg | grep -Ei 'sensorhub|hf_manager|scp_sensor' | tail -60; "
             "/usr/local/bin/lynx-status --assert-ready >/dev/null", timeout=20)
        report["state"] = "sensorhub-modules-loaded-interfaces-unverified"
    except Exception as exc:
        report.update(state="failed-or-incomplete", error=str(exc))
    report["finished_ns"] = time.time_ns()
    save()
    print(json.dumps({"state": report["state"], "receipt": str(out / "result.json"),
                      "error": report.get("error")}))
    if report["state"] != "sensorhub-modules-loaded-interfaces-unverified":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
