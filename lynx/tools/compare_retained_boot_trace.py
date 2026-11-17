#!/usr/bin/env python3
"""Match retained expdb stage lines to a pinned SSH boot file, without printing logs."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
V50_SHA = "6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59"
BOOT_ID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")
PRINTABLE = re.compile(rb"[\x20-\x7e]{20,}")


def lines_from_expdb(data):
    region = data[0x3000:0xE3000]
    return [match.group() for match in PRINTABLE.finditer(region)
            if match.group().startswith(b"LYNX_WIFI uptime=")]


def digest(lines):
    return hashlib.sha256(b"\n".join(lines)).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--boot-id", required=True)
    args = parser.parse_args()
    capture = args.capture.resolve(strict=True)
    if not capture.is_relative_to(ROOT / "logs") or \
            not BOOT_ID.fullmatch(args.boot_id):
        parser.error("capture must be in Lynx logs and boot ID must be UUID format")
    raw = capture.read_bytes()
    if len(raw) != 0xF0000:
        raise ValueError("capture is not a complete expdb prefix")
    remote = f"/var/log/lynx/boot-{args.boot_id}.log"
    command = ("set -eu; test \"$(sha256sum /dev/sdc39 | cut -c1-64)\" = " +
               V50_SHA + "; cat " + remote)
    argv = ssh_command("192.168.100.107", command)
    argv[-2:-2] = ["-p", "2222"]
    result = subprocess.run(argv, capture_output=True, timeout=15)
    if result.returncode or not 1 <= len(result.stdout) <= 65536:
        raise RuntimeError("pinned V50 boot file read failed")
    retained = lines_from_expdb(raw)
    boot_lines = [line for line in result.stdout.splitlines()
                  if line.startswith(b"LYNX_WIFI uptime=")]
    out = ROOT / "logs" / f"retained-boot-match-{time.time_ns()}"
    out.mkdir(mode=0o700)
    (out / "boot.log").write_bytes(result.stdout)
    report = {"state": "compared", "phone_writes": False,
              "capture": str(capture), "capture_sha256": hashlib.sha256(raw).hexdigest(),
              "boot_id": args.boot_id, "remote_boot_file": remote,
              "boot_file_sha256": hashlib.sha256(result.stdout).hexdigest(),
              "retained_stage_lines": len(retained), "boot_stage_lines": len(boot_lines),
              "retained_stage_sha256": digest(retained),
              "boot_stage_sha256": digest(boot_lines),
              "exact_stage_match": retained == boot_lines}
    (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"],
                      "receipt": str(out / "result.json"),
                      "retained_stage_lines": len(retained),
                      "boot_stage_lines": len(boot_lines),
                      "exact_stage_match": report["exact_stage_match"]}))


if __name__ == "__main__":
    main()
