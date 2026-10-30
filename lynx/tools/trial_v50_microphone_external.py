#!/usr/bin/env python3
"""Compare quiet and external-clap microphone levels; no PCM leaves Lynx."""

import argparse
import json
from pathlib import Path
import re
import socket
import statistics
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
BOOT = "6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59"
REPLY = re.compile(r"NRP/1 1 OK value=(\d+) detail=rms_x100=(\d+) peak=(\d+) duration_ms=1000 external_validated=0")


def health():
    args = ssh_command("192.168.100.107", "uname -r; sha256sum /dev/sdc39; "
                       "/usr/local/bin/lynx-status --assert-ready")
    args[-2:-2] = ["-p", "2222"]
    result = subprocess.run(args, capture_output=True, text=True, timeout=20)
    if result.returncode:
        raise RuntimeError("Lynx health or SSH check failed")
    lines = result.stdout.splitlines()
    if (lines[0] != "5.10.149-android12-9-o-g311738fbb5a8" or
        lines[1].split()[0] != BOOT):
        raise RuntimeError("Lynx V50 identity changed")
    state = json.loads(next(line for line in lines if line.startswith("{")))
    if state["issues"] or state["battery"]["capacity_percent"] < 25:
        raise RuntimeError("Lynx health guard failed")
    return state


def sample():
    started_wall_ns = time.time_ns()
    started_monotonic = time.monotonic()
    with socket.create_connection(("192.168.100.107", 4243), timeout=8) as conn:
        conn.settimeout(8)
        conn.sendall(b"NRP/1 1 CALL MIC_LEVEL\n")
        data = bytearray()
        while b"\n" not in data and len(data) < 1024:
            chunk = conn.recv(1024)
            if not chunk:
                break
            data.extend(chunk)
    text = data.split(b"\n", 1)[0].decode("ascii", errors="replace")
    match = REPLY.fullmatch(text)
    if not match or match.group(1) != match.group(2):
        raise RuntimeError("microphone level response invalid")
    return {"started_wall_ns": started_wall_ns,
            "elapsed_seconds": round(time.monotonic() - started_monotonic, 3),
            "rms_x100": int(match.group(1)), "peak": int(match.group(3))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("quiet", "clap"))
    parser.add_argument("--quiet-receipt", type=Path)
    args = parser.parse_args()
    if args.mode == "clap" and not args.quiet_receipt:
        parser.error("clap mode needs --quiet-receipt")
    receipt = ROOT / "logs" / f"v50-microphone-{args.mode}-{time.time_ns()}.json"
    report = {"mode": args.mode, "state": "preflight", "raw_audio_retained": False,
              "boot_partition_writes": False, "samples": []}
    try:
        before = health()
        report["boot_id"] = before["boot_id"]
        if args.mode == "clap":
            quiet = json.loads(args.quiet_receipt.read_text())
            if (quiet.get("mode") != "quiet" or quiet.get("state") != "completed" or
                quiet.get("boot_id") != report["boot_id"]):
                raise RuntimeError("quiet baseline absent or from another boot")
            baseline = statistics.median(item["rms_x100"] for item in quiet["samples"])
            report["quiet_receipt"] = str(args.quiet_receipt)
            report["quiet_median_rms_x100"] = baseline
        count = 3 if args.mode == "quiet" else 5
        for _ in range(count):
            report["samples"].append(sample())
        after = health()
        if after["boot_id"] != report["boot_id"] or after["issues"]:
            raise RuntimeError("Lynx health changed")
        if args.mode == "clap":
            rms = [item["rms_x100"] for item in report["samples"]]
            report["max_rms_x100"] = max(rms)
            report["ratio_to_quiet"] = round(max(rms) / max(1, baseline), 2)
            report["external_response_candidate"] = max(rms) >= max(2000, 3 * baseline)
        report["state"] = "completed"
    except Exception as exc:
        report.update(state="failed", error=str(exc))
    receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"], "receipt": str(receipt),
                      "ratio_to_quiet": report.get("ratio_to_quiet"),
                      "external_response_candidate": report.get("external_response_candidate"),
                      "error": report.get("error")}))
    if report["state"] != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
