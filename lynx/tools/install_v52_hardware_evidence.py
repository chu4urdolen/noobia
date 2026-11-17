#!/usr/bin/env python3
"""Update Lynx's read-only GNSS/Bluetooth inventory after V52 trials."""

import hashlib
import json
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "tools/lynx_hardware.py"
BOOT = "9206aafb339ad66b2d942ea5795b8f476a5eaf3a148f9cdfc76be22cb83e30bf"
OLD = "6a5cb9b0a163996e92e371c84642114451e2744bfd51e3a67153e95151804737"
TARGET = "/usr/local/bin/lynx_hardware.py"
BACKUP = TARGET + ".before-v52-connectivity-evidence"


def remote(command, data=None):
    args = ssh_command("192.168.100.107", command)
    args[-2:-2] = ["-p", "2222"]
    return subprocess.run(args, input=data, capture_output=True, timeout=25)


def main():
    receipt = ROOT / "logs" / f"v52-hardware-evidence-{time.time_ns()}.json"
    report = {"state": "preflight", "boot_partition_writes": False,
              "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(), "steps": []}
    installed = False

    def step(name, command, data=None):
        result = remote(command, data)
        report["steps"].append({"name": name, "exit": result.returncode,
                                "stdout": result.stdout.decode(errors="replace")[-900:],
                                "stderr": result.stderr.decode(errors="replace")[-300:]})
        if result.returncode:
            raise RuntimeError(name + " failed")
        return result.stdout.decode(errors="replace").strip()

    try:
        if remote(f"test -e {BACKUP}").returncode == 0:
            raise RuntimeError("rollback copy already exists")
        hashes = step("identity", f"sha256sum /dev/sdc39 {TARGET}").splitlines()
        if len(hashes) != 2 or [line.split()[0] for line in hashes] != [BOOT, OLD]:
            raise RuntimeError("V52 or inventory identity changed")
        health = json.loads(step("health_before", "/usr/local/bin/lynx-status --assert-ready"))
        if health["issues"] or health["battery"]["capacity_percent"] < 25:
            raise RuntimeError("phone health guard failed")
        source = SOURCE.read_bytes()
        step("stage", "set -eu; cat > /run/lynx_hardware_v52.py; "
             f'test "$(sha256sum /run/lynx_hardware_v52.py | cut -c1-64)" = {report["source_sha256"]}; '
             "/usr/bin/python3 -m py_compile /run/lynx_hardware_v52.py", source)
        installed = True  # The remote update may complete before SSH reports an error.
        step("install", f"set -eu; test \"$(sha256sum /dev/sdc39 | cut -c1-64)\" = {BOOT}; "
             f"test \"$(sha256sum {TARGET} | cut -c1-64)\" = {OLD}; "
             f"cp -p {TARGET} {BACKUP}; "
             f"cp /run/lynx_hardware_v52.py {TARGET}.next; chmod 755 {TARGET}.next; "
             f"mv {TARGET}.next {TARGET}; rc-service lynx-noobd restart")
        bt = json.loads(step("bluetooth_status", "/usr/local/bin/lynx-hardware status bluetooth"))
        if (not bt["interface_ready"] or bt["validated"] or
                not bt["evidence"]["stpbt"] or bt["evidence"]["hci"] or
                not bt["evidence"]["nexus_le_connection_trial_verified"]):
            raise RuntimeError("Bluetooth evidence mismatch")
        gps = json.loads(step("gnss_status", "/usr/local/bin/lynx-hardware status gnss"))
        if (not gps["interface_ready"] or gps["validated"] or
                not gps["evidence"]["nmea_trial_verified"] or
                gps["evidence"]["position_fix_verified"]):
            raise RuntimeError("GNSS evidence mismatch")
        after = json.loads(step("health_after", "/usr/local/bin/lynx-status --assert-ready"))
        if after["boot_id"] != health["boot_id"] or after["issues"]:
            raise RuntimeError("Alpine health changed")
        report["state"] = "installed-and-verified"
    except Exception as exc:
        report.update(state="failed", error=str(exc))
        if installed:
            rollback = remote(f"if test -f {BACKUP}; then cp -p {BACKUP} {TARGET}; "
                              "rc-service lynx-noobd restart; fi")
            report["rollback_exit"] = rollback.returncode
    receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"], "receipt": str(receipt),
                      "error": report.get("error")}))
    if report["state"] != "installed-and-verified":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
