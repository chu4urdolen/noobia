#!/usr/bin/env python3
"""Update Lynx's GNSS node inventory and restart NRP/1 safely."""

import hashlib
import json
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "tools/lynx_hardware.py"
BOOT = "6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59"


def remote(command, data=None):
    args = ssh_command("192.168.100.107", command)
    args[-2:-2] = ["-p", "2222"]
    return subprocess.run(args, input=data, capture_output=True, timeout=25)


def main():
    receipt = ROOT / "logs" / f"v50-gnss-node-status-{time.time_ns()}.json"
    report = {"state": "preflight", "boot_partition_writes": False, "steps": []}
    old = None
    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()

    def step(name, command, data=None, accept=(0,)):
        result = remote(command, data)
        report["steps"].append({"name": name, "exit": result.returncode,
                                "stdout": result.stdout.decode(errors="replace")[-500:],
                                "stderr": result.stderr.decode(errors="replace")[-300:]})
        if result.returncode not in accept:
            raise RuntimeError(name + " failed")
        return result.stdout.decode(errors="replace").strip()

    try:
        if remote("test -e /usr/local/bin/lynx_hardware.py.before-gnss-node-status").returncode == 0:
            raise RuntimeError("GNSS status fix already applied; preserve its rollback")
        identity = step("identity", "sha256sum /dev/sdc39 /usr/local/bin/lynx_hardware.py")
        hashes = [line.split()[0] for line in identity.splitlines()]
        if len(hashes) != 2 or hashes[0] != BOOT:
            raise RuntimeError("V50 boot identity changed")
        old = hashes[1]
        report["previous_sha256"] = old
        health = json.loads(step("health", "/usr/local/bin/lynx-status --assert-ready"))
        if health["issues"] or health["battery"]["capacity_percent"] < 25:
            raise RuntimeError("Alpine health guard failed")
        step("stage", "cat > /run/lynx_hardware.py.next; "
             f'test "$(sha256sum /run/lynx_hardware.py.next | cut -c1-64)" = {digest}; '
             "/usr/bin/python3 -m py_compile /run/lynx_hardware.py.next", SOURCE.read_bytes())
        step("install", f"set -eu; test \"$(sha256sum /dev/sdc39 | cut -c1-64)\" = {BOOT}; "
             f"test \"$(sha256sum /usr/local/bin/lynx_hardware.py | cut -c1-64)\" = {old}; "
             "cp -p /usr/local/bin/lynx_hardware.py "
             "/usr/local/bin/lynx_hardware.py.before-gnss-node-status; "
             "cp /run/lynx_hardware.py.next /usr/local/bin/lynx_hardware.py.next; "
             "chmod 755 /usr/local/bin/lynx_hardware.py.next; "
             "mv /usr/local/bin/lynx_hardware.py.next /usr/local/bin/lynx_hardware.py; "
             "rc-service lynx-noobd restart")
        result = json.loads(step("status", "/usr/local/bin/lynx-hardware status microphone"))
        if not result["interface_ready"]:
            raise RuntimeError("microphone interface disappeared")
        step("invalid_request", "printf '{\"action\":\"record\"}\\n' | "
             "/usr/local/share/lynx-tools/calls/lynx_microphone_level.sh", accept=(2,))
        if "this tool currently accepts" not in report["steps"][-1]["stderr"]:
            raise RuntimeError("unexpected local tool rejection")
        step("service", "rc-service lynx-noobd status")
        after = json.loads(step("health_after", "/usr/local/bin/lynx-status --assert-ready"))
        if after["boot_id"] != health["boot_id"] or after["issues"]:
            raise RuntimeError("Alpine health changed")
        report["state"] = "installed-and-verified"
    except Exception as exc:
        report.update(state="failed", error=str(exc))
        if old:
            recovery = remote("if test -f /usr/local/bin/lynx_hardware.py.before-gnss-node-status; "
                              "then cp -p /usr/local/bin/lynx_hardware.py.before-gnss-node-status "
                              "/usr/local/bin/lynx_hardware.py; rc-service lynx-noobd restart; fi")
            report["rollback_exit"] = recovery.returncode
    receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"], "receipt": str(receipt),
                      "error": report.get("error")}))
    if report["state"] != "installed-and-verified":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
