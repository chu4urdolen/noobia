#!/usr/bin/env python3
"""Stage C2 Camera Repeatability Trial Script for Lynx (SPEC C2, #292, #309).

Runs Stage B frame capture multiple times (default 10) on a single boot,
attended with Noob present, without the emergency reboot net firing.
Measures:
- Measured frame validity (size == 1600*1200 and non-flat statistics via decode_camera_bayer).
- YUV-B interrupt delta (detects IRQ leakage or storm).
- Battery capacity (capacity_percent) and thermal envelope (max_mC).
- Kernel stability: bounded Oops / BUG check per iteration.
- Safe subprocess timeout handling (remote 55s watchdog warning).

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
MIN_BATTERY_PERCENT = 20
MAX_TEMP_C = 65.0


def compute_frame_statistics(raw_bytes: bytes, width: int = 1600, height: int = 1200) -> dict:
    """Compute basic pixel statistics to verify frame is non-flat and genuine."""
    expected = width * height
    if len(raw_bytes) != expected:
        raise ValueError(f"expected {expected} Bayer bytes, got {len(raw_bytes)}")

    # Histogram over 256 bins
    counts = [0] * 256
    for b in raw_bytes:
        counts[b] += 1

    min_val = next((i for i, c in enumerate(counts) if c > 0), 0)
    max_val = next((i for i in range(255, -1, -1) if counts[i] > 0), 255)
    mean_val = sum(i * c for i, c in enumerate(counts)) / float(expected)
    dominant_val = max(range(256), key=lambda i: counts[i])
    dominant_frac = counts[dominant_val] / float(expected)
    unique_vals = sum(1 for c in counts if c > 0)

    is_valid = (unique_vals >= 2) and (max_val > min_val) and (dominant_frac < 0.99)

    return {
        "bytes": len(raw_bytes),
        "width": width,
        "height": height,
        "min": min_val,
        "max": max_val,
        "mean": round(mean_val, 2),
        "unique_values": unique_vals,
        "dominant_value": dominant_val,
        "dominant_fraction": round(dominant_frac, 4),
        "valid": is_valid,
    }


def get_yuv_b_irq_count(ssh_fn) -> int:
    """Read cam_yuv_b interrupt count over SSH."""
    rc, out, _ = ssh_fn("grep cam_yuv_b /proc/interrupts || true")
    if rc != 0 or not out:
        return 0
    parts = out.split()
    total = 0
    for p in parts[1:]:
        if p.isdigit():
            total += int(p)
    return total


def check_kernel_oops(ssh_fn) -> tuple[bool, int]:
    """Check for kernel Oops/BUG via dmesg. Returns (has_oops, count)."""
    rc, out, _ = ssh_fn('dmesg | grep -c -E "Oops|BUG:|Unable to handle" || true')
    count = 0
    if rc == 0 and out.strip():
        try:
            count = int(out.strip().splitlines()[-1].strip())
        except ValueError:
            count = 0
    return count > 0, count


def read_lynx_health(ssh_fn) -> dict:
    """Read health JSON from /usr/local/bin/lynx-status."""
    rc, out, _ = ssh_fn("/usr/local/bin/lynx-status")
    if rc != 0 or not out:
        return {}
    try:
        data = json.loads(out)
        battery = data.get("battery", {})
        thermal = data.get("thermal", {})

        cap_pct = battery.get("capacity_percent")
        if cap_pct is None:
            cap_pct = battery.get("capacity_pct")

        max_mc = thermal.get("max_mC")
        temp_c = (max_mc / 1000.0) if max_mc is not None else thermal.get("shell_max_c")

        return {
            "battery_percent": cap_pct,
            "temp_c": temp_c,
            "raw": data,
        }
    except (ValueError, TypeError):
        return {}


def find_latest_trial_result(logs_root: Path, boot_id: str) -> Path | None:
    """Find the newest camera-camsv-frame-* directory for this boot."""
    if not logs_root.is_dir():
        return None
    dirs = sorted(logs_root.glob("camera-camsv-frame-*"), key=lambda p: p.stat().st_mtime, reverse=True)
    for d in dirs:
        res_file = d / "result.json"
        if res_file.is_file():
            try:
                data = json.loads(res_file.read_text())
                steps = data.get("steps", [])
                for s in steps:
                    if s.get("name") == "boot_id":
                        boot_id_file = d / "boot_id.stdout"
                        b = boot_id_file.read_text().strip() if boot_id_file.is_file() else ""
                        if b == boot_id or not boot_id:
                            return d
            except Exception:
                pass
    return None


def run_c2_trial(
    boot_id: str,
    iterations: int = DEFAULT_ITERATIONS,
    settle_s: float = DEFAULT_SETTLE_S,
    attended: bool = True,
    output_dir: Path | None = None,
    ssh_fn=None,
    camsv_cmd_fn=None,
    logs_root: Path = LOGS_DIR,
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
    has_oops, oops_count = check_kernel_oops(ssh)

    report["initial_health"] = {
        "battery_percent": init_health.get("battery_percent"),
        "temp_c": init_health.get("temp_c"),
        "initial_irq": init_irq,
        "initial_oops": oops_count,
    }

    if has_oops:
        report["state"] = "aborted_initial_oops"
        report["error"] = f"kernel Oops/BUG detected in preflight ({oops_count} matches)"
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
        return report

    successful = 0
    total_irq_growth = 0
    prev_irq = init_irq

    for idx in range(1, iterations + 1):
        iter_record: dict = {
            "index": idx,
            "start_time": time.time(),
        }

        # Health trend gating before iteration
        cur_health = read_lynx_health(ssh)
        bat = cur_health.get("battery_percent")
        temp = cur_health.get("temp_c")
        if bat is not None and bat < MIN_BATTERY_PERCENT:
            iter_record["error"] = f"battery {bat}% below safety gate {MIN_BATTERY_PERCENT}%"
            report["iterations"].append(iter_record)
            report["state"] = "aborted_battery_depleted"
            break
        if temp is not None and temp > MAX_TEMP_C:
            iter_record["error"] = f"temperature {temp:.1f}C exceeded safety gate {MAX_TEMP_C}C"
            report["iterations"].append(iter_record)
            report["state"] = "aborted_thermal_exceeded"
            break

        # 1. Run single frame capture
        frame_stats = None
        if camsv_cmd_fn:
            res_tuple = camsv_cmd_fn(idx)
            cap_ok, cap_bytes, cap_msg = res_tuple[0], res_tuple[1], res_tuple[2]
            if len(res_tuple) > 3:
                frame_stats = res_tuple[3]
        else:
            cmd = [
                sys.executable,
                str(REPO / "lynx" / "tools" / "trial_camera_camsv_frame.py"),
                "--attended",
                "--boot-id",
                boot_id,
            ]
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                cap_ok = (res.returncode == 0)
                cap_msg = res.stdout if cap_ok else res.stderr
                cap_bytes = 0

                # Read actual captured frame from the trial receipt
                trial_dir = find_latest_trial_result(logs_root, boot_id)
                if trial_dir:
                    cand_frame = trial_dir / "sensor4.bayer"
                    if not cand_frame.is_file():
                        cand_frame = trial_dir / "download_frame.stdout"
                    if cand_frame.is_file():
                        raw_data = cand_frame.read_bytes()
                        cap_bytes = len(raw_data)
                        frame_stats = compute_frame_statistics(raw_data)
                        if not frame_stats.get("valid"):
                            cap_ok = False
                            cap_msg = f"frame in {cand_frame} failed validity check (flat image)"
            except subprocess.TimeoutExpired:
                cap_ok = False
                cap_bytes = 0
                cap_msg = "TimeoutExpired: Stage B capture timed out after 60s"
                iter_record["error"] = "capture timed out; remote watchdog may still fire - wait 60 s"
                report["iterations"].append(iter_record)
                report["state"] = f"aborted_timeout_iteration_{idx}"
                report["warning"] = "remote 55s watchdog may still fire - wait at least 60 s before any further action"
                (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
                return report

        current_irq = get_yuv_b_irq_count(ssh)
        irq_delta = current_irq - prev_irq
        prev_irq = current_irq
        total_irq_growth += max(0, irq_delta)

        # Check for kernel Oops after capture
        has_oops, oops_count = check_kernel_oops(ssh)

        iter_record["cap_ok"] = cap_ok
        iter_record["frame_bytes"] = cap_bytes
        iter_record["frame_stats"] = frame_stats
        iter_record["irq_delta"] = irq_delta
        iter_record["current_irq"] = current_irq
        iter_record["oops_detected"] = has_oops
        iter_record["msg"] = cap_msg[:200] if cap_msg else ""

        if not cap_ok:
            iter_record["error"] = "capture failed or frame invalid"
            report["iterations"].append(iter_record)
            report["state"] = f"aborted_at_iteration_{idx}"
            break

        if has_oops:
            iter_record["error"] = f"kernel Oops detected after iteration ({oops_count} matches)"
            report["iterations"].append(iter_record)
            report["state"] = f"aborted_oops_at_iteration_{idx}"
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
        "battery_percent": final_health.get("battery_percent"),
        "temp_c": final_health.get("temp_c"),
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
