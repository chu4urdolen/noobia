#!/usr/bin/env python3
"""Guarded V52 Bluetooth GATT or OpenRC update; no radio or boot write."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
COMPONENTS = {
    "sessions": (ROOT / "tools/lynx_ble_gatt_probe.py", "/usr/local/bin/lynx-ble-gatt",
                 "14592d500a1619b3e8071272ce7a3e6a07ce9db8e6da900901b67225553a2518",
                 "reconnect", "PYTHONPATH=/usr/local/lib/lynx-bluetooth "
                 "/usr/bin/python3 -m py_compile"),
    "supervisor": (ROOT / "tools/lynx-bluetooth-openrc.sh", "/etc/init.d/lynx-bluetooth",
                   "c204f5571e454e46a88ad6f7bd643857a26abf64ca1063e88b51721c52d214c4",
                   "supervisor", "/bin/sh -n"),
}
BOOT_SHA = "9206aafb339ad66b2d942ea5795b8f476a5eaf3a148f9cdfc76be22cb83e30bf"


def phone(command, payload=None, timeout=15):
    argv = ssh_command("192.168.100.107", command)
    argv[-2:-2] = ["-p", "2222"]
    return subprocess.run(argv, input=payload, capture_output=True, timeout=timeout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("component", choices=COMPONENTS)
    parser.add_argument("--rollback", action="store_true")
    args = parser.parse_args()
    source, target, old_sha, label, syntax_check = COMPONENTS[args.component]
    backup = target + ".before-" + label
    receipt = ROOT / "logs" / f"v52-bluetooth-{args.component}-{time.time_ns()}"
    receipt.mkdir(mode=0o700)
    report = {"state": "preflight", "component": args.component,
              "rollback": args.rollback,
              "partition_writes": False, "radio_started": False, "steps": []}
    candidate = source.read_bytes()
    new_sha = hashlib.sha256(candidate).hexdigest()

    def step(name, command, payload=None, timeout=15):
        result = phone(command, payload=payload, timeout=timeout)
        (receipt / (name + ".stdout")).write_bytes(result.stdout)
        (receipt / (name + ".stderr")).write_bytes(result.stderr)
        report["steps"].append({"name": name, "exit": result.returncode})
        (receipt / "result.json").write_text(json.dumps(report, indent=2) + "\n")
        if result.returncode:
            raise RuntimeError(name + " failed")
        return result.stdout.decode()

    try:
        status = json.loads(step("health_before", "/usr/local/bin/lynx-status --assert-ready"))
        if status["issues"] or status["battery"]["capacity_percent"] < 50 or \
                status["thermal"]["max_mC"] >= 45000:
            raise RuntimeError("Alpine or power preflight failed")
        report["boot_id"] = status["boot_id"]
        step("identity", "set -eu; test \"$(sha256sum /dev/sdc39 | cut -c1-64)\" = "
             + BOOT_SHA + "; ! rc-service lynx-bluetooth status >/dev/null 2>&1")
        if args.rollback:
            step("rollback", "set -eu; test \"$(sha256sum " + target +
                 " | cut -c1-64)\" = " + new_sha + "; test \"$(sha256sum " +
                 backup + " | cut -c1-64)\" = " + old_sha + "; cp -p " +
                 backup + " " + target + "; test \"$(sha256sum " + target +
                 " | cut -c1-64)\" = " + old_sha)
            report["state"] = "rolled-back"
        else:
            step("old_hash", "set -eu; test \"$(sha256sum " + target +
                 " | cut -c1-64)\" = " + old_sha + "; test ! -e " + backup)
            stage = "/run/lynx-bt-" + label + "-" + str(time.time_ns())
            step("stage", "set -eu; umask 077; cat > " + stage + "; "
                 "test \"$(sha256sum " + stage + " | cut -c1-64)\" = " + new_sha +
                 "; " + syntax_check + " " + stage, candidate)
            step("install", "set -eu; cp -p " + target + " " + backup +
                 "; install -m 755 " + stage + " " + target + "; rm -f " + stage +
                 "; test \"$(sha256sum " + target + " | cut -c1-64)\" = " + new_sha +
                 "; test \"$(sha256sum " + backup + " | cut -c1-64)\" = " + old_sha)
            report["state"] = "installed-awaiting-trial"
        after = json.loads(step("health_after", "/usr/local/bin/lynx-status --assert-ready"))
        if after["issues"] or after["boot_id"] != report["boot_id"]:
            raise RuntimeError("Alpine health changed")
    except Exception as exc:
        report.update(state="failed", error=str(exc))
    (receipt / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"], "receipt": str(receipt / "result.json"),
                      "error": report.get("error")}))
    if report["state"] not in ("rolled-back", "installed-awaiting-trial"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
