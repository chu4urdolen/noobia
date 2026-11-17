#!/usr/bin/env python3
"""Select sensor4 -> seninf-1 -> CAMSV-0 in RAM, without streaming."""

import json
import argparse
from pathlib import Path
import shlex
import subprocess
import sys
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent


def remote(command, timeout=20):
    argv = ssh_command("192.168.100.107", command)
    argv[-2:-2] = ["-p", "2222"]
    result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"remote exit {result.returncode}: {result.stderr.strip()}")
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boot-id", required=True)
    args = parser.parse_args()
    receipt = ROOT / "logs" / f"camera-camsv-route-{time.time_ns()}.json"
    report = {"schema": 1, "boot_partition_writes": False,
              "camera_stream_requested": False, "steps": []}

    def save():
        receipt.write_text(json.dumps(report, indent=2) + "\n")

    def step(name, command):
        output = remote(command)
        report["steps"].append({"name": name, "command": command,
                                "output": output[-25000:]})
        save()
        return output

    try:
        if step("boot_id", "cat /proc/sys/kernel/random/boot_id").strip() != args.boot_id:
            raise RuntimeError("boot changed; route not applied")
        health = json.loads(step("health", "/usr/local/bin/lynx-status --assert-ready"))
        if health["issues"] or health["battery"]["capacity_percent"] < 25:
            raise RuntimeError("health gate failed")
        graph = step("graph_before", "media-ctl -d /dev/media1 -p")
        seninf = graph.split("entity 27: seninf-1", 1)[1].split("\n- entity ", 1)[0]
        if '"mtk-cam raw-0":0 [ENABLED,DYNAMIC]' in seninf:
            step("disable_raw0", "media-ctl -d /dev/media1 -l " + shlex.quote("27:1->105:0[4]"))
        if '"sensor4":0 [ENABLED,DYNAMIC]' not in seninf:
            step("enable_sensor4", "media-ctl -d /dev/media1 -l " + shlex.quote("45:0->27:0[5]"))
        if '"mtk-cam camsv-0":0 [ENABLED,DYNAMIC]' not in seninf:
            step("enable_camsv0", "media-ctl -d /dev/media1 -l " + shlex.quote("27:1->615:0[5]"))
        graph = step("graph_after", "media-ctl -d /dev/media1 -p")
        seninf = graph.split("entity 27: seninf-1", 1)[1].split("\n- entity ", 1)[0]
        if ('"mtk-cam raw-0":0 [DYNAMIC]' not in seninf or
                '"mtk-cam camsv-0":0 [ENABLED,DYNAMIC]' not in seninf):
            raise RuntimeError("route verification failed")
        report["state"] = "camsv_route_linked_no_stream"
    except Exception as exc:
        report["state"] = "failed"
        report["error"] = str(exc)
    finally:
        save()
    print(json.dumps({"state": report["state"], "receipt": str(receipt),
                      "error": report.get("error")}))
    if report["state"] != "camsv_route_linked_no_stream":
        sys.exit(1)


if __name__ == "__main__":
    main()
