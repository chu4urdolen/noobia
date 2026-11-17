#!/usr/bin/env python3
"""Read and validate persistent Lynx boot-stage logs over pinned Alpine SSH."""

import base64
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from capture_v46_bootdiag import BOOT_ID, FRAME, REMOTE
from lynx_wifi_v19_contact import ssh_command
from parse_v38_persistent_trace import parse


ROOT = Path(__file__).resolve().parent.parent
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boot-id", required=True, help="current verified Alpine boot ID")
    parser.add_argument("--ip", choices=("192.168.100.7", "192.168.100.8"),
                        default="192.168.100.7")
    args = parser.parse_args()
    if not BOOT_ID.fullmatch(args.boot_id):
        parser.error("invalid boot ID")
    os.umask(0o077)
    out = ROOT / "logs" / f"v48-bootdiag-capture-{time.time_ns()}"
    out.mkdir(mode=0o700)
    identity = ("set -eu; cat /proc/sys/kernel/random/boot_id; "
                "cat /etc/alpine-release; readlink /proc/1/exe")
    command = ssh_command(args.ip, identity)
    command[-2:-2] = ["-p", "2222"]
    check = subprocess.run(command, capture_output=True, timeout=20)
    lines = check.stdout.decode(errors="replace").splitlines()
    if (check.returncode or len(lines) != 3 or lines[0] != args.boot_id or
            lines[1] != "3.24.2" or lines[2] != "/sbin/openrc-init" or
            not BOOT_ID.fullmatch(lines[0])):
        raise ValueError("Fresh V48 Alpine identity did not match")
    command = ssh_command(args.ip, REMOTE)
    command[-2:-2] = ["-p", "2222"]
    captured = subprocess.run(command, capture_output=True, timeout=40)
    (out / "capture.stdout").write_bytes(captured.stdout)
    (out / "capture.stderr").write_bytes(captured.stderr)
    if captured.returncode or len(captured.stdout) > 2_000_000:
        raise ValueError("Bootdiag capture failed or exceeded limit")
    records = out / "records"
    records.mkdir(mode=0o700)
    parsed = []
    cursor = 0
    while cursor < len(captured.stdout) and captured.stdout != b"NO_LOG_DIR\n":
        match = FRAME.match(captured.stdout, cursor)
        if not match:
            raise ValueError("Bootdiag framing invalid")
        name, count, digest, encoded = match.groups()
        data = base64.b64decode(encoded, validate=True)
        if len(data) != int(count) or hashlib.sha256(data).hexdigest().encode() != digest:
            raise ValueError("Bootdiag checksum or size invalid")
        path = records / name.decode()
        if path.exists():
            raise ValueError("Duplicate bootdiag record")
        path.write_bytes(data)
        parsed.append(parse(path))
        cursor = match.end()
    report = {"state": "verified", "current_boot_id": args.boot_id,
              "phone_ip": args.ip, "phone_writes": False, "records": parsed,
              "captured_at_ns": time.time_ns()}
    result = out / "result.json"
    result.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"], "records": len(parsed),
                      "result": str(result)}))


if __name__ == "__main__":
    main()
