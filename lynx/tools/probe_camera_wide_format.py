#!/usr/bin/env python3
"""Attended format-only IMX355 probe; restores macro route and V4L format."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
SWITCH = ROOT / "tools/switch_camera_camsv_route.py"


def remote(command):
    argv = ssh_command("192.168.100.107", command)
    argv[-2:-2] = ["-p", "2222"]
    return subprocess.run(argv, capture_output=True, text=True, timeout=15)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boot-id", required=True)
    parser.add_argument("--attended", action="store_true", required=True)
    args = parser.parse_args()
    out = ROOT / "logs" / f"camera-wide-format-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"schema": 1, "stream_requested": False,
              "boot_partition_writes": False, "boot_id": args.boot_id, "steps": []}
    route_wide = False
    format_changed = False

    def step(name, command, check=True):
        result = remote(command)
        (out / f"{name}.stdout").write_text(result.stdout)
        (out / f"{name}.stderr").write_text(result.stderr)
        report["steps"].append({"name": name, "command": command,
                                "exit": result.returncode})
        if check and result.returncode:
            raise RuntimeError(f"{name} exit {result.returncode}: "
                               f"{(result.stdout + result.stderr).strip()}")
        return result.stdout

    def switch(sensor):
        cmd = [sys.executable, str(SWITCH), "--boot-id", args.boot_id,
               "--target-sensor", str(sensor), "--execute", "--attended"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
        report["steps"].append({"name": f"route_{sensor}", "exit": result.returncode,
                                "stdout": result.stdout, "stderr": result.stderr})
        if result.returncode:
            raise RuntimeError(f"route {sensor} failed: {result.stdout} {result.stderr}")

    try:
        if step("boot_id", "cat /proc/sys/kernel/random/boot_id").strip() != args.boot_id:
            raise RuntimeError("boot identity changed")
        before = step("format_before", "v4l2-ctl -d /dev/video145 --get-fmt-video")
        if "1600/1200" not in before or "'BA81'" not in before:
            raise RuntimeError("unexpected baseline capture format")
        switch(2)
        route_wide = True
        format_changed = True
        step("set_wide", "v4l2-ctl -d /dev/video145 --set-fmt-video=width=3264,height=2448,pixelformat=BA81")
        fmt = step("format_wide", "v4l2-ctl -d /dev/video145 --get-fmt-video")
        graph = step("graph_wide", "media-ctl -d /dev/media1 -p")
        if "3264/2448" not in fmt or "'BA81'" not in fmt:
            raise RuntimeError("capture node rejected wide geometry")
        if '-> "mtk-cam camsv-0":0 [ENABLED,DYNAMIC]' not in graph:
            raise RuntimeError("wide graph lost CAMSV link")
        report["state"] = "wide_format_accepted_no_stream"
    except Exception as exc:
        report["state"] = "failed"
        report["error"] = str(exc)
    finally:
        if format_changed:
            try:
                step("restore_format", "v4l2-ctl -d /dev/video145 --set-fmt-video=width=1600,height=1200,pixelformat=BA81")
                restored = step("format_restored", "v4l2-ctl -d /dev/video145 --get-fmt-video")
                if "1600/1200" not in restored or "'BA81'" not in restored:
                    raise RuntimeError("capture format restoration mismatch")
            except Exception as exc:
                report["restore_format_error"] = str(exc)
                report["state"] = "restore_failed"
        if route_wide:
            try:
                switch(4)
            except Exception as exc:
                report["restore_route_error"] = str(exc)
                report["state"] = "restore_failed"
        try:
            step("health_final", "/usr/local/bin/lynx-status --assert-ready")
        except Exception as exc:
            report["health_final_error"] = str(exc)
            report["state"] = "restore_failed"
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"], "receipt": str(out / "result.json"),
                      "error": report.get("error")}))
    if report["state"] != "wide_format_accepted_no_stream":
        sys.exit(1)


if __name__ == "__main__":
    main()
