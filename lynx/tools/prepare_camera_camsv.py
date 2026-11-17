#!/usr/bin/env python3
"""Prepare Lynx's reviewed GC02M1 CAMSV route after a healthy V53 boot.

This stages modules only in RAM. It never streams the camera or writes boot
partitions. A physical attendant is required for the live preparation path.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
HOST = "192.168.100.107"
EXPECTED_BOOT_SHA = "c047455271828cf9bfa90984eea121d8ede8754f6297fc06f33f1e99fb23c75e"
EXPECTED_ISP_SHA = "0910503d465a9ea51b70a6b501fc7dead5f2eafd1f7d5a17845b1056eb5d9b3e"


def remote(command, timeout=30):
    argv = ssh_command(HOST, command)
    argv[-2:-2] = ["-p", "2222"]
    result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"Alpine SSH command failed ({result.returncode}): {result.stderr[-300:]}")
    return result.stdout


def snapshot():
    lines = remote("cat /proc/sys/kernel/random/boot_id; sha256sum /dev/sdc39 | cut -c1-64; "
                   "cat /sys/module/firmware_class/parameters/path; "
                   "/usr/local/bin/lynx-status --assert-ready").splitlines()
    if len(lines) != 4 or lines[1] != EXPECTED_BOOT_SHA or lines[2] != "/vendor/firmware":
        raise RuntimeError("unexpected boot image, firmware path, or status output")
    health = json.loads(lines[3])
    if health["boot_id"] != lines[0] or health["issues"]:
        raise RuntimeError("Lynx health gate failed")
    if health["battery"]["capacity_percent"] < 35 or health["battery"]["temperature_mC"] >= 35000:
        raise RuntimeError("battery gate failed")
    if health["thermal"]["max_mC"] >= 45000:
        raise RuntimeError("thermal gate failed")
    modules = remote("cat /proc/modules")
    return {"boot_id": lines[0], "health": health,
            "isp_loaded": "mtk_cam_isp " in modules,
            "sensor_loaded": "imgsensor " in modules}


def verified_isp_receipt(boot_id):
    for path in sorted((ROOT / "logs").glob("camera-isp-patched-trial-*/result.json"), reverse=True):
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if (data.get("state") == "stable_35_seconds_no_capture" and
                data.get("boot_id") == boot_id and
                data.get("candidate_sha256") == EXPECTED_ISP_SHA and
                data.get("sensor_power_patch") is True):
            return path
    return None


def route_ready():
    graph = remote("media-ctl -d /dev/media1 -p", timeout=20)
    if "entity 27: seninf-1" not in graph:
        return False
    section = graph.split("entity 27: seninf-1", 1)[1].split("\n- entity ", 1)[0]
    return ('"sensor4":0 [ENABLED,DYNAMIC]' in section and
            '"mtk-cam camsv-0":0 [ENABLED,DYNAMIC]' in section and
            '"mtk-cam raw-0":0 [ENABLED,DYNAMIC]' not in section)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--status", action="store_true", help="read-only readiness check")
    mode.add_argument("--execute", action="store_true", help="load missing RAM modules and link route")
    parser.add_argument("--attended", action="store_true", help="Noob is present for Fastboot recovery")
    args = parser.parse_args()
    if args.execute and not args.attended:
        parser.error("--execute requires --attended")
    os.umask(0o077)
    out = ROOT / "logs" / f"camera-prepare-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"schema": 1, "state": "starting", "boot_partition_writes": False,
              "camera_stream_requested": False, "steps": []}

    def save():
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")

    def stage(label, script, *arguments):
        argv = [sys.executable, str(ROOT / "tools" / script), *arguments]
        result = subprocess.run(argv, capture_output=True, text=True, timeout=240)
        (out / f"{label}.stdout").write_text(result.stdout)
        (out / f"{label}.stderr").write_text(result.stderr)
        report["steps"].append({"name": label, "exit": result.returncode,
                                "command": [script, *arguments]})
        save()
        if result.returncode:
            raise RuntimeError(f"{label} failed; see {out}")
        try:
            return json.loads(result.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            raise RuntimeError(f"{label} gave no parseable receipt")

    try:
        before = snapshot()
        report["boot_id"] = before["boot_id"]
        report["battery_percent"] = before["health"]["battery"]["capacity_percent"]
        receipt = verified_isp_receipt(before["boot_id"])
        if before["isp_loaded"] and not receipt:
            raise RuntimeError("loaded ISP has no verified matching-boot patched receipt")
        ready = before["isp_loaded"] and before["sensor_loaded"] and route_ready()
        report["state"] = "already_prepared" if ready else "not_prepared"
        report["isp_receipt"] = str(receipt) if receipt else None
        save()
        if args.execute and not ready:
            if not before["isp_loaded"]:
                stage("camera_stock_prefix", "probe_camera_ram.py", "--through", "mtk-cam-plat-mt6983")
                stage("camera_pipeline_prefix", "probe_camera_pipeline_ram.py", "--through", "mtk_printk_ctrl")
                stage("isp_preflight", "trial_camera_isp_patched.py", "--preflight-only", "--with-sensor-power")
                stage("isp_load", "trial_camera_isp_patched.py", "--execute", "--attended", "--with-sensor-power")
            current = snapshot()
            if current["boot_id"] != before["boot_id"]:
                raise RuntimeError("boot changed during preparation")
            receipt = verified_isp_receipt(current["boot_id"])
            if not current["isp_loaded"] or not receipt:
                raise RuntimeError("patched ISP verification missing")
            if not route_ready():
                stage("camsv_route", "configure_camera_camsv_route.py", "--boot-id", current["boot_id"])
            final = snapshot()
            if final["boot_id"] != before["boot_id"] or not route_ready():
                raise RuntimeError("camera route or boot changed during preparation")
            report["isp_receipt"] = str(receipt)
            report["state"] = "prepared_no_stream"
    except Exception as exc:
        report["state"] = "failed"
        report["error"] = str(exc)
    save()
    print(json.dumps({"state": report["state"], "receipt": str(out / "result.json"),
                      "error": report.get("error")}))
    if report["state"] == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
