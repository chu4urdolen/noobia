#!/usr/bin/env python3
"""Capture bounded camera-trial health and IRQ snapshots on Nexus."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
HOST = "192.168.100.107"
PORT = "2222"
COMMAND = (
    "cat /proc/sys/kernel/random/boot_id; echo __MODULES__; "
    "grep -E '^(mtk_cam_isp|imgsensor|mtk_imgsys_v4l2) ' /proc/modules || true; "
    "echo __INTERRUPTS__; cat /proc/interrupts; "
    "echo __SOFTIRQS__; cat /proc/softirqs; "
    "echo __HEALTH__; /usr/local/bin/lynx-status --assert-ready"
)


def sample():
    command = ssh_command(HOST, COMMAND)
    command[-2:-2] = ["-p", PORT]
    result = subprocess.run(command, capture_output=True, timeout=15)
    return result


def irq_counts(snapshot):
    lines = snapshot.splitlines()
    start = lines.index("__INTERRUPTS__") + 1
    end = lines.index("__SOFTIRQS__")
    counts = {}
    for line in lines[start:end]:
        parts = line.split()
        if (len(parts) >= 9 and parts[0].endswith(":") and
                all(value.isdigit() for value in parts[1:9])):
            counts[parts[0][:-1]] = {
                "cpus": [int(value) for value in parts[1:9]],
                "description": " ".join(parts[9:])}
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration-seconds", type=int, default=90)
    parser.add_argument("--interval-seconds", type=int, default=2)
    args = parser.parse_args()
    if not 5 <= args.duration_seconds <= 300 or not 1 <= args.interval_seconds <= 10:
        parser.error("duration must be 5..300 seconds and interval 1..10 seconds")
    os.umask(0o077)
    out = ROOT / "logs" / f"camera-health-window-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"schema": 1, "mode": "read-only-irq-health-window",
              "duration_seconds": args.duration_seconds,
              "interval_seconds": args.interval_seconds, "samples": []}
    deadline = time.monotonic() + args.duration_seconds
    first_boot = None
    while time.monotonic() < deadline:
        number = len(report["samples"])
        started = time.time_ns()
        try:
            result = sample()
            stdout = result.stdout.decode(errors="replace")
            lines = stdout.splitlines()
            boot = lines[0] if lines else None
            health = None
            if "__HEALTH__" in lines:
                try:
                    health = json.loads("\n".join(lines[lines.index("__HEALTH__") + 1:]))
                except (ValueError, TypeError):
                    pass
            (out / f"sample-{number:03d}.txt").write_text(stdout)
            (out / f"sample-{number:03d}.stderr").write_bytes(result.stderr[-4096:])
            item = {"number": number, "started_unix_ns": started,
                    "ssh_exit": result.returncode, "boot_id": boot,
                    "health_issues": health.get("issues") if health else None,
                    "battery_percent": health.get("battery", {}).get("capacity_percent")
                    if health else None}
            if first_boot is None and boot:
                first_boot = boot
            if boot and boot != first_boot:
                item["boot_changed"] = True
                report["samples"].append(item)
                break
        except (OSError, subprocess.SubprocessError) as exc:
            item = {"number": number, "started_unix_ns": started,
                    "error": str(exc)}
        report["samples"].append(item)
        delay = min(args.interval_seconds, deadline - time.monotonic())
        if delay > 0:
            time.sleep(delay)
    report["boot_id"] = first_boot
    valid = [item for item in report["samples"] if item.get("ssh_exit") == 0
             and item.get("boot_id") == first_boot]
    if len(valid) >= 2:
        before = irq_counts((out / f"sample-{valid[0]['number']:03d}.txt").read_text())
        after = irq_counts((out / f"sample-{valid[-1]['number']:03d}.txt").read_text())
        growth = []
        for irq in before.keys() & after.keys():
            delta = [end - start for start, end in zip(before[irq]["cpus"],
                                                         after[irq]["cpus"])]
            if any(value < 0 for value in delta):
                continue
            growth.append({"irq": irq, "description": after[irq]["description"],
                           "cpu0_delta": delta[0], "total_delta": sum(delta)})
        report["top_irq_growth"] = sorted(growth, key=lambda row: row["total_delta"],
                                           reverse=True)[:12]
        report["camera_irq_growth"] = sorted(
            (row for row in growth if any(name in row["description"]
             for name in ("seninf_top", "cam_raw_", "cam_yuv_", "camsv", "mraw"))),
            key=lambda row: row["total_delta"], reverse=True)
    report["state"] = ("captured" if any(
        item.get("ssh_exit") == 0 and item.get("boot_id")
        for item in report["samples"]) else "no-valid-samples")
    (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"], "samples": len(report["samples"]),
                      "receipt": str(out / "result.json")}))
    if report["state"] != "captured":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
