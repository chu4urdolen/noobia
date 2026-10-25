#!/usr/bin/env python3
"""Install Lynx's proven display tools to Alpine without lighting the panel.

The installer verifies the V49 rescue image, stock module hashes, Alpine
health, and the on-phone atomic binary. It adds only files under /usr/local.
It does not enable a service, reboot, write boot partitions, or show pixels.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_v47_display_bootstrap import MODULES, MODULE_DIR, KERNEL
from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
IP = "192.168.100.7"
INIT_SHA = "b560f233f5ecf838b5e948d0cd3685b676a84f3097adb00d2c8bfa6e5446ab1f"
ATOMIC_SHA = "0406aa15f90547d571271efdba5cd7566277dfb5e4e56f209c5c1f7e9d9271e5"
ATOMIC_SOURCE = "/var/lib/lynx-devroot/tmp/lynx_drm_atomic_candidate"
REMOTE_BASE = "/usr/local/lib/lynx-display"


def ssh(command, payload=None, port=2222, timeout=30):
    argv = ssh_command(IP, command)
    argv[-2:-2] = ["-p", str(port)]
    return subprocess.run(argv, input=payload, capture_output=True, timeout=timeout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true", help="copy verified files to Alpine")
    args = parser.parse_args()
    os.umask(0o077)
    out = ROOT / "logs" / f"v49-display-bundle-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "starting", "install": args.install,
              "boot_partition_writes": False, "service_enabled": False,
              "visual_trial": False, "steps": []}

    def step(label, command, payload=None, port=2222, timeout=30):
        result = ssh(command, payload, port=port, timeout=timeout)
        (out / f"{label}.stdout").write_bytes(result.stdout)
        (out / f"{label}.stderr").write_bytes(result.stderr)
        report["steps"].append({"name": label, "exit": result.returncode})
        if result.returncode:
            raise RuntimeError(f"{label} failed; see saved output")
        return result.stdout.decode(errors="replace")

    try:
        sources = []
        for name, expected, _ in MODULES:
            path = MODULE_DIR / (name + ".ko")
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != expected:
                raise RuntimeError(f"stock module hash mismatch: {name}")
            sources.append((name, expected, data))
        scripts = {
            "lynx-display-prepare": ROOT / "linux-port/lynx-display-prepare.sh",
            "lynx-display-show": ROOT / "linux-port/lynx-display-show.sh",
        }
        for name, path in scripts.items():
            subprocess.run(["sh", "-n", str(path)], check=True)
        report["stock_module_count"] = len(sources)
        identity = step("identity", "cat /proc/sys/kernel/random/boot_id; "
                        "uname -r; sha256sum /init | cut -c1-64", port=22).splitlines()
        if len(identity) != 3 or identity[1] != KERNEL or identity[2] != INIT_SHA:
            raise RuntimeError("V49 rescue/kernel identity mismatch")
        report["boot_id"] = identity[0]
        health = json.loads(step("health", "/usr/local/bin/lynx-status --assert-ready"))
        if health["boot_id"] != identity[0] or health["battery"]["capacity_percent"] < 20:
            raise RuntimeError("Alpine health, boot ID, or battery preflight failed")
        report["battery_percent"] = health["battery"]["capacity_percent"]
        if not args.install:
            report["state"] = "checked-no-install"
        else:
            step("directories", f"mkdir -p {REMOTE_BASE}/modules")
            for name, expected, data in sources:
                target = f"{REMOTE_BASE}/modules/{name}.ko"
                command = (f"set -eu; cat > {target}.new; "
                           f'test "$(sha256sum {target}.new | cut -c1-64)" = "{expected}"; '
                           f"chmod 644 {target}.new; mv {target}.new {target}")
                step(f"module_{name}", command, payload=data, timeout=45)
            copy_binary = (
                "set -eu; "
                f'test "$(sha256sum {ATOMIC_SOURCE} | cut -c1-64)" = "{ATOMIC_SHA}"; '
                f"cp {ATOMIC_SOURCE} {REMOTE_BASE}/lynx_drm_atomic_candidate.new; "
                f'chmod 755 {REMOTE_BASE}/lynx_drm_atomic_candidate.new; '
                f"mv {REMOTE_BASE}/lynx_drm_atomic_candidate.new "
                f"{REMOTE_BASE}/lynx_drm_atomic_candidate"
            )
            step("atomic_binary", copy_binary)
            for name, path in scripts.items():
                data = path.read_bytes()
                digest = hashlib.sha256(data).hexdigest()
                target = f"/usr/local/bin/{name}"
                command = (f"set -eu; cat > {target}.new; "
                           f'test "$(sha256sum {target}.new | cut -c1-64)" = "{digest}"; '
                           f"chmod 755 {target}.new; mv {target}.new {target}")
                step(name, command, payload=data)
            step("prepare_idempotent", "/usr/local/bin/lynx-display-prepare", timeout=60)
            step("atomic_test_only", "/usr/local/bin/lynx-display-show --check", timeout=25)
            report["state"] = "installed-readonly-validated"
    except Exception as exc:
        report.update(state="failed-or-incomplete", error=str(exc))
    report["finished_ns"] = time.time_ns()
    path = out / "result.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"], "result": str(path)}))
    if report["state"] not in ("checked-no-install", "installed-readonly-validated"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
