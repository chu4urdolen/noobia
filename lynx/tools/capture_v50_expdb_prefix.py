#!/usr/bin/env python3
"""Read Lynx's first 0xF0000 expdb bytes on exact V50, compare retained logs."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
V50_SHA = "6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59"
BASELINE = ROOT / "logs/expdb-prefix-1792332639175907933/expdb-first-0xf0000.raw"
BASELINE_SHA = "2f2023f2b39c26a5caee9e84161d03b762ed1ec547a3b0477c38a7f17dbb9152"
LENGTH = 0xF0000
REGIONS = {"ramconsole": (0x2000, 0x1000), "pstore": (0x3000, 0xE0000)}


def phone(command, timeout=25):
    argv = ssh_command("192.168.100.107", command)
    argv[-2:-2] = ["-p", "2222"]
    return subprocess.run(argv, capture_output=True, timeout=timeout)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    os.umask(0o077)
    out = ROOT / "logs" / f"v50-expdb-after-v52-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "preflight", "partition_writes": False,
              "source": "/dev/sdc7", "length": LENGTH}
    try:
        baseline = BASELINE.read_bytes()
        if len(baseline) != LENGTH or sha(baseline) != BASELINE_SHA:
            raise RuntimeError("baseline length or hash differs")
        identity = phone("set -eu; sha256sum /dev/sdc39 | cut -c1-64; "
                         "cat /sys/class/block/sdc7/uevent; "
                         "cat /sys/class/block/sdc7/size; "
                         "blockdev --getsize64 /dev/sdc7; "
                         "cat /proc/sys/kernel/random/boot_id")
        (out / "identity.stdout").write_bytes(identity.stdout)
        (out / "identity.stderr").write_bytes(identity.stderr)
        lines = identity.stdout.decode().splitlines()
        if identity.returncode or not lines or lines[0] != V50_SHA or \
                "PARTNAME=expdb" not in lines or "262144" not in lines or \
                "134217728" not in lines:
            raise RuntimeError("V50 or expdb identity differs")
        report["boot_id"] = lines[-1]
        read = phone("dd if=/dev/sdc7 bs=4096 count=240 iflag=fullblock status=none", 45)
        (out / "read.stderr").write_bytes(read.stderr)
        if read.returncode or len(read.stdout) != LENGTH:
            raise RuntimeError("expdb prefix read incomplete")
        (out / "expdb-first-0xf0000.raw").write_bytes(read.stdout)
        report["prefix_sha256"] = sha(read.stdout)
        report["baseline_sha256"] = sha(baseline)
        report["regions"] = {}
        for name, (offset, length) in REGIONS.items():
            old = baseline[offset:offset + length]
            new = read.stdout[offset:offset + length]
            report["regions"][name] = {
                "changed": old != new, "sha256": sha(new),
                "changed_bytes": sum(a != b for a, b in zip(old, new)),
            }
        report["state"] = "captured-compared"
    except Exception as exc:
        report.update(state="failed", error=str(exc))
    (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"],
                      "receipt": str(out / "result.json"),
                      "regions": report.get("regions"),
                      "error": report.get("error")}))
    if report["state"] != "captured-compared":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
