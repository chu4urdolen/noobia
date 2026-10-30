#!/usr/bin/env python3
"""Stage matching stock driver modules in Lynx RAM without loading any."""

import hashlib
import json
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
GRAPH = ROOT / "logs/hardware-dependencies-1793303434757393031.json"
GAP = ROOT / "logs/hardware-live-gap-1793304049573421464.json"
BOOT = "6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59"
STAGE = "/run/lynx-hardware-modules"


def phone(command, data=None, timeout=25):
    args = ssh_command("192.168.100.107", command)
    args[-2:-2] = ["-p", "2222"]
    return subprocess.run(args, input=data, capture_output=True, timeout=timeout)


def main():
    receipt = ROOT / "logs" / f"v50-hardware-modules-staged-{time.time_ns()}.json"
    report = {"state": "preflight", "partition_writes": False,
              "modules_loaded": False, "stage": STAGE, "files": []}
    try:
        graph = json.loads(GRAPH.read_text())
        gap = json.loads(GAP.read_text())
        if gap["source"] != str(GRAPH.relative_to(ROOT)):
            raise RuntimeError("dependency graph and live gap differ")
        missing = sorted({name for group in gap["missing_by_group"].values() for name in group})
        if len(missing) != 14:
            raise RuntimeError("expected 14 absent stock modules")
        identity = phone("cat /proc/sys/kernel/random/boot_id; sha256sum /dev/sdc39; "
                         "/usr/local/bin/lynx-status --assert-ready", timeout=20)
        if identity.returncode:
            raise RuntimeError("Lynx health check failed")
        lines = identity.stdout.decode().splitlines()
        if lines[0] != gap["boot_id"] or lines[1].split()[0] != BOOT:
            raise RuntimeError("Lynx boot changed since dependency comparison")
        health = json.loads(next(line for line in lines if line.startswith("{")))
        if health["issues"] or health["battery"]["capacity_percent"] < 25:
            raise RuntimeError("health guard failed")
        if phone(f"mkdir -p {STAGE}; chmod 700 {STAGE}").returncode:
            raise RuntimeError("could not create RAM stage")
        for name in missing:
            info = graph["modules"][name]
            if not info["kernel_matches"]:
                raise RuntimeError("module kernel mismatch: " + name)
            local = ROOT / info["path"]
            payload = local.read_bytes()
            digest = hashlib.sha256(payload).hexdigest()
            if digest != info["sha256"]:
                raise RuntimeError("stock module hash changed: " + name)
            remote = f"{STAGE}/{name}.ko"
            result = phone(f"umask 077; cat > {remote}.part; "
                           f'test "$(sha256sum {remote}.part | cut -c1-64)" = {digest}; '
                           f"mv {remote}.part {remote}", payload, timeout=40)
            if result.returncode:
                raise RuntimeError("module staging failed: " + name)
            report["files"].append({"module": name, "sha256": digest,
                                    "size": len(payload), "remote": remote})
        after = phone("cat /proc/sys/kernel/random/boot_id; "
                      "/usr/local/bin/lynx-status --assert-ready", timeout=20)
        if after.returncode or after.stdout.decode().splitlines()[0] != gap["boot_id"]:
            raise RuntimeError("Lynx health changed after staging")
        report["state"] = "staged-in-ram-not-loaded"
    except Exception as exc:
        report.update(state="failed", error=str(exc))
    receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"], "count": len(report["files"]),
                      "receipt": str(receipt), "error": report.get("error")}))
    if report["state"] != "staged-in-ram-not-loaded":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
