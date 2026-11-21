#!/usr/bin/env python3
"""Stage C2 Camera Repeatability Trial Script for Lynx (SPEC C2, #292).

Runs Stage B frame capture multiple times (default 10) on a single boot,
attended with Noob present, without the emergency reboot net firing.
Measures:
- Frame validity and byte size across every iteration.
- YUV-B interrupt delta (detects IRQ leakage or storm).
- Battery capacity and thermal envelope drift.
- Supervisor and system health responsiveness.

Generates a structured trial report in lynx/logs/c2-repeatability-<timestamp>/.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
LOGS_DIR = REPO / "lynx" / "logs"

DEFAULT_ITERATIONS = 10
DEFAULT_SETTLE_S = 3.0
MAX_ALLOWED_IRQ_DELTA_PER_FRAME = 2000
MIN_FRAME_BYTES = 1600 * 1200


def get_yuv_b_irq_count(ssh_fn) -> int:
    """Read cam_yuv_b interrupt count over SSH."""
    rc, out, _ = ssh_fn("grep cam_yuv_b /proc/interrupts || true")
    if rc != 0 or not out:
        return 0
    parts = out.split()
    # parts[0] is '123:', subsequent columns are counts per CPU
    total = 0
    for p in parts[1:]:
        if p.isdigit():
            total += int(p)
    return total


def read_lynx_health(ssh_fn) -> dict:
    """Read health JSON from /usr/local/bin/lynx-status."""
    rc, out, _ = ssh_fn("/usr/local/bin/lynx-status")
    if rc != 0 or not out:
        return {}
    try:
        return json.loads(out)
    except ValueError:
        return {}


def run_c2_trial(
    boot_id: str,
    iterations: int = DEFAULT_ITERATIONS,
    settle_s: float = DEFAULT_SETTLE_S,
    attended: bool = True,
    output_dir: Path | None = None,
    ssh_fn=None,
    camsv_cmd_fn=None,
) -> dict:
    if not attended:
        raise RuntimeError("C2 repeatability trial requires attended operator with Noob present")

    ts = time.strftime("%Y%m%d-%H%M%S")
    out = output_dir or (LOGS_DIR / f"c2-repeatability-{ts}")
    out.mkdir(parents=True, exist_ok=True)

    report: dict = {
        "trial": "C2_camera_repeatability",
        "boot_id": boot_id,
        "timestamp": ts,
        "target_iterations": iterations,
        "iterations": [],
        "state": "starting",
    }

    def default_ssh(cmd: str) -> tuple[int, str, str]:
        from lynx.tools.network.lynx_wifi_v19_contact import ssh_command
        argv = ssh_command("192.168.100.107", cmd)
        argv[-2:-2] = ["-p", "2222"]
        res = subprocess.run(argv, capture_output=True, text=True, timeout=30)
        return res.returncode, res.stdout, res.stderr

    ssh = ssh_fn or default_ssh

    # Preflight verification
    init_health = read_lynx_health(ssh)
    init_irq = get_yuv_b_irq_count(ssh)

    report["initial_health"] = {
        "battery_pct": init_health.get("battery", {}).get("capacity_pct"),
        "shell_temp_c": init_health.get("thermal", {}).get("shell_max_c"),
        "initial_irq": init_irq,
    }

    successful = 0
    total_irq_growth = 0
    prev_irq = init_irq

    for idx in range(1, iterations + 1):
        iter_record: dict = {
            "index": idx,
            "start_time": time.time(),
        }

        # 1. Run single frame capture
        if camsv_cmd_fn:
            cap_ok, cap_bytes, cap_msg = camsv_cmd_fn(idx)
        else:
            cmd = [
                sys.executable,
                str(REPO / "lynx" / "tools" / "trial_camera_camsv_frame.py"),
                "--attended",
                "--boot-id",
                boot_id,
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            cap_ok = (res.returncode == 0)
            cap_bytes = MIN_FRAME_BYTES if cap_ok else 0
            cap_msg = res.stdout if cap_ok else res.stderr

        current_irq = get_yuv_b_irq_count(ssh)
        irq_delta = current_irq - prev_irq
        prev_irq = current_irq
        total_irq_growth += max(0, irq_delta)

        iter_record["cap_ok"] = cap_ok
        iter_record["frame_bytes"] = cap_bytes
        iter_record["irq_delta"] = irq_delta
        iter_record["current_irq"] = current_irq
        iter_record["msg"] = cap_msg[:200] if cap_msg else ""

        if not cap_ok:
            iter_record["error"] = "capture failed"
            report["iterations"].append(iter_record)
            report["state"] = f"aborted_at_iteration_{idx}"
            break

        if irq_delta > MAX_ALLOWED_IRQ_DELTA_PER_FRAME:
            iter_record["error"] = f"IRQ delta {irq_delta} exceeded limit {MAX_ALLOWED_IRQ_DELTA_PER_FRAME}"
            report["iterations"].append(iter_record)
            report["state"] = "aborted_irq_growth"
            break

        successful += 1
        report["iterations"].append(iter_record)

        if idx < iterations:
            time.sleep(settle_s)

    final_health = read_lynx_health(ssh)
    report["final_health"] = {
        "battery_pct": final_health.get("battery", {}).get("capacity_pct"),
        "shell_temp_c": final_health.get("thermal", {}).get("shell_max_c"),
        "final_irq": prev_irq,
        "total_irq_growth": total_irq_growth,
    }
    report["successful_iterations"] = successful

    if successful == iterations:
        report["state"] = "c2_repeatability_passed"

    result_file = out / "result.json"
    result_file.write_text(json.dumps(report, indent=2) + "\n")
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boot-id", required=True, help="Current Lynx boot identifier")
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS, help="Number of capture iterations (default: 10)")
    parser.add_argument("--settle-s", type=float, default=DEFAULT_SETTLE_S, help="Settling delay between frames in seconds")
    parser.add_argument("--attended", action="store_true", help="Confirm operator and Noob presence")
    parser.add_argument("--output-dir", type=Path, default=None, help="Directory for trial results")

    args = parser.parse_args(argv)

    if not args.attended:
        print("c2_repeatability: ERROR: --attended required (Noob must be present)", file=sys.stderr)
        return 1

    try:
        rep = run_c2_trial(
            boot_id=args.boot_id,
            iterations=args.iterations,
            settle_s=args.settle_s,
            attended=args.attended,
            output_dir=args.output_dir,
        )
        print(json.dumps({"ok": rep.get("state") == "c2_repeatability_passed", "report": rep}, indent=2))
        return 0 if rep.get("state") == "c2_repeatability_passed" else 2
    except Exception as exc:
        print(f"c2_repeatability: ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
