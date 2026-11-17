#!/usr/bin/env python3
"""Save Lynx's camera nodes, modules, IRQs, and recent kernel messages.

Do not add V4L2 sensor-control enumeration here: --list-ctrls-menus caused
a vendor-kernel Oops on 2026-11-04. See CAMERA-CTRL-CRASH-20261104.md.
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
REMOTE = r'''
import json
from pathlib import Path
import platform
import subprocess
import sys

def read(path):
    try:
        return path.read_text(errors="replace").strip()
    except (OSError, UnicodeError):
        return None

def class_entries(name):
    base = Path("/sys/class") / name
    result = []
    for item in sorted(base.glob("*")):
        device = item / "device"
        driver = device / "driver"
        result.append({
            "node": item.name,
            "name": read(item / "name"),
            "dev": read(item / "dev"),
            "device": str(device.resolve()) if device.exists() else None,
            "driver": driver.resolve().name if driver.exists() else None,
        })
    return result

def camera_devices():
    base = Path("/sys/bus/platform/devices")
    result = []
    for item in sorted(base.iterdir()):
        if not (item.name.startswith("1a0") or item.name.startswith("1a1")):
            continue
        if not any(word in item.name for word in ("cam", "seninf", "mraw")):
            continue
        driver = item / "driver"
        result.append({
            "name": item.name,
            "driver": driver.resolve().name if driver.exists() else None,
            "runtime_status": read(item / "power/runtime_status"),
            "runtime_usage": read(item / "power/runtime_usage"),
            "power_control": read(item / "power/control"),
        })
    return result

messages = subprocess.run(["dmesg"], capture_output=True, text=True,
                          errors="replace", timeout=8)
camera_words = ("camisp", "seninf", "cam_raw", "cam_yuv", "imgsensor", "ccd", "camera")
report = {
    "schema": 1,
    "boot_id": read(Path("/proc/sys/kernel/random/boot_id")),
    "kernel": platform.release(),
    "uptime": read(Path("/proc/uptime")),
    "modules": [line for line in (read(Path("/proc/modules")) or "").splitlines()
                if any(word in line.lower() for word in camera_words + ("mtk_cam",))],
    "video4linux": class_entries("video4linux"),
    "media": class_entries("media"),
    "media_device_nodes": sorted(str(p) for p in Path("/dev").glob("media[0-9]*")),
    "camera_devices": camera_devices(),
    "nodes": sorted(str(p) for pattern in ("media*", "video*", "v4l-subdev*")
                    for p in Path("/dev").glob(pattern)),
    "camera_irqs": [line for line in (read(Path("/proc/interrupts")) or "").splitlines()
                    if any(word in line for word in ("seninf", "cam_raw", "cam_yuv", "camsv", "mraw"))],
    "recent_camera_messages": [line for line in messages.stdout.splitlines()
                               if any(word in line.lower() for word in camera_words)][-100:],
    "dmesg_exit": messages.returncode,
}
if "--media-graph" in sys.argv[1:]:
    report["media_graphs"] = {}
    for node in sorted(Path("/dev").glob("media*")):
        try:
            graph = subprocess.run(["media-ctl", "--print-topology", "-d", str(node)],
                                   capture_output=True, text=True, errors="replace", timeout=3)
            report["media_graphs"][str(node)] = {
                "exit": graph.returncode, "stdout": graph.stdout[:100000],
                "stderr": graph.stderr[:4000]}
        except (OSError, subprocess.TimeoutExpired) as exc:
            report["media_graphs"][str(node)] = {"error": str(exc)}
    try:
        devices = subprocess.run(["v4l2-ctl", "--list-devices"],
                                 capture_output=True, text=True, errors="replace", timeout=3)
        report["v4l2_list_devices"] = {"exit": devices.returncode,
                                        "stdout": devices.stdout[:100000],
                                        "stderr": devices.stderr[:4000]}
    except (OSError, subprocess.TimeoutExpired) as exc:
        report["v4l2_list_devices"] = {"error": str(exc)}
print(json.dumps(report))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expect-isp", action="store_true",
                        help="fail if the ISP module or V4L2 nodes are absent")
    parser.add_argument("--media-graph", action="store_true",
                        help="query media topology after a stable ISP trial")
    args = parser.parse_args()
    command = ssh_command("192.168.100.107",
                          "python3 - --media-graph" if args.media_graph else "python3 -")
    command[-2:-2] = ["-p", "2222"]
    result = subprocess.run(command, input=REMOTE, capture_output=True,
                            text=True, errors="replace", timeout=20)
    if result.returncode:
        raise SystemExit("Lynx inventory failed: " + result.stderr[-300:])
    report = json.loads(result.stdout)
    if report["kernel"] != "5.10.149-android12-9-o-g311738fbb5a8":
        raise SystemExit("unexpected Lynx kernel")
    os.umask(0o077)
    out = ROOT / "logs" / f"camera-runtime-inventory-{time.time_ns()}.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    isp = any(line.startswith("mtk_cam_isp ") for line in report["modules"])
    print(json.dumps({"receipt": str(out), "boot_id": report["boot_id"],
                      "isp_loaded": isp, "video_nodes": len(report["video4linux"]),
                      "media_nodes": len(report["media_device_nodes"])}))
    if args.expect_isp and (not isp or not report["video4linux"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
