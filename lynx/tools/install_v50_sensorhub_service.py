#!/usr/bin/env python3
"""Stage matching Nord 3 sensorhub modules and an optional Alpine service."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
STOCK = ROOT / "linux-port/artifacts/stock-cph2493-August-eu-ota/wifi-reference/vendor-dlkm-unpacked/lib/modules"
MODULES = {
    "hf_manager": "6556d801250d2f7c21d55542337df7b7f4793ecce48551603525b52d0617e677",
    "sensorhub": "10eede8b4673d3cc81894ed76fa7a044eec10e90b52464483848bda10d93154e",
}
BOOT = "6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59"
KERNEL = "5.10.149-android12-9-o-g311738fbb5a8"
INIT = "b560f233f5ecf838b5e948d0cd3685b676a84f3097adb00d2c8bfa6e5446ab1f"
SERVICE = b'''#!/sbin/openrc-run
description="Lynx MediaTek sensorhub"

depend() {
    need lynx-audio
    after lynx-haptic
}

start() {
    ebegin "Loading Lynx sensorhub"
    /usr/local/bin/lynx-sensorhub-bootstrap > /var/log/lynx-sensorhub-bootstrap.log 2>&1
    eend $?
}

stop() {
    ebegin "Leaving Lynx sensorhub idle"
    eend 0
}
'''


def ssh(command, data=None, port=2222, timeout=20):
    args = ssh_command("192.168.100.107", command)
    args[-2:-2] = ["-p", str(port)]
    return subprocess.run(args, input=data, capture_output=True, timeout=timeout)


def main():
    out = ROOT / "logs" / f"v50-sensorhub-service-install-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "preflight", "boot_partition_writes": False, "steps": []}

    def step(name, command, data=None, port=2222, timeout=20):
        result = ssh(command, data, port, timeout)
        (out / f"{name}.stdout").write_bytes(result.stdout)
        (out / f"{name}.stderr").write_bytes(result.stderr)
        report["steps"].append({"name": name, "exit": result.returncode})
        if result.returncode:
            raise RuntimeError(f"{name} failed; see receipt")
        return result.stdout.decode(errors="replace").strip()

    try:
        identity = step("identity", "cat /proc/sys/kernel/random/boot_id; "
                        "uname -r; sha256sum /init /dev/sdc39 | cut -c1-64",
                        port=22, timeout=25).splitlines()
        if len(identity) != 4 or identity[1:] != [KERNEL, INIT, BOOT]:
            raise RuntimeError("not verified V50")
        report["boot_id"] = identity[0]
        health = json.loads(step("health", "/usr/local/bin/lynx-status --assert-ready"))
        b = health["battery"]
        if (health["boot_id"] != identity[0] or b["capacity_percent"] < 50 or
            b["temperature_mC"] >= 35000 or health["thermal"]["max_mC"] >= 45000 or
            health["root_free_mib"] < 400):
            raise RuntimeError("sensorhub installation health guard failed")
        step("preflight", "set -eu; rc-service lynx-audio status; "
             "test -c /dev/hf_manager; grep -q '^sensorhub ' /proc/modules; "
             "test ! -e /etc/init.d/lynx-sensorhub; "
             "test ! -e /var/lib/lynx-sensors/v1")
        step("directory", "mkdir -p /var/lib/lynx-sensors; mkdir -m 700 /var/lib/lynx-sensors/v1")
        for name, digest in MODULES.items():
            path = STOCK / (name + ".ko")
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != digest:
                raise RuntimeError(f"stock checksum mismatch: {name}")
            magic = subprocess.run(["modinfo", "-F", "vermagic", str(path)],
                                   capture_output=True, text=True, check=True).stdout.strip()
            if not magic.startswith(KERNEL + " "):
                raise RuntimeError(f"kernel ABI mismatch: {name}")
            remote = f"/var/lib/lynx-sensors/v1/{name}.ko"
            step(name + "_stage", f"cat > {remote}; chmod 600 {remote}", data, timeout=35)
            step(name + "_verify", f'test "$(sha256sum {remote} | cut -c1-64)" = {digest}')
        for local, remote in (
            (ROOT / "tools/lynx-sensorhub-bootstrap.sh", "/usr/local/bin/lynx-sensorhub-bootstrap"),
            (ROOT / "tools/lynx_hf_sample.py", "/usr/local/bin/lynx-hf-sample"),
        ):
            data = local.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            step(local.stem + "_install",
                 f'cat > {remote}; test "$(sha256sum {remote} | cut -c1-64)" = {digest}; chmod 755 {remote}',
                 data)
        step("service_install", "cat > /etc/init.d/lynx-sensorhub; chmod 755 /etc/init.d/lynx-sensorhub",
             SERVICE)
        step("service_start", "rc-service lynx-sensorhub start; rc-service lynx-sensorhub status; "
             "/usr/local/bin/lynx-status --assert-ready >/dev/null")
        step("enable", "rc-update add lynx-sensorhub default; "
             "test -L /etc/runlevels/default/lynx-sensorhub")
        report["state"] = "installed-and-enabled-awaiting-cold-boot"
    except Exception as exc:
        report.update(state="failed-or-incomplete", error=str(exc))
    (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"], "receipt": str(out / "result.json"),
                      "error": report.get("error")}))
    if report["state"] != "installed-and-enabled-awaiting-cold-boot":
        sys.exit(1)


if __name__ == "__main__":
    main()
