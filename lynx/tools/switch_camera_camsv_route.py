#!/usr/bin/env python3
"""Guarded RAM-only CAMSV route switch between Lynx macro and wide cameras."""

import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time

from camera_route_plan import ROUTES, link_descriptor, plan_route
from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent


def remote(command, timeout=15):
    argv = ssh_command("192.168.100.107", command)
    argv[-2:-2] = ["-p", "2222"]
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)


def entity_block(graph, entity, name):
    marker = f"- entity {entity}: {name} "
    return graph.split(marker, 1)[1].split("\n- entity ", 1)[0]


def detect_route(graph):
    states = {}
    for sensor, (sensor_link, camsv_link) in ROUTES.items():
        source = entity_block(graph, sensor_link[0], f"sensor{sensor}")
        seninf = entity_block(graph, sensor_link[2], f"seninf-{sensor - 3 if sensor == 4 else sensor}")
        sensor_active = f'-> "seninf-{1 if sensor == 4 else 2}":0 [ENABLED,DYNAMIC]' in source
        camsv_active = '-> "mtk-cam camsv-0":0 [ENABLED,DYNAMIC]' in seninf
        states[sensor] = {"sensor": sensor_active, "camsv": camsv_active}
    if states[4] == {"sensor": True, "camsv": True} and states[2] == {"sensor": False, "camsv": False}:
        return 4
    if states[2] == {"sensor": True, "camsv": True} and states[4] == {"sensor": False, "camsv": False}:
        return 2
    return None


def run_step(report, name, command, check=True):
    result = remote(command)
    if name.startswith("graph") or name == "rollback_graph":
        (Path(report["directory"]) / f"{name}.txt").write_text(result.stdout)
    report["steps"].append({"name": name, "command": command,
                            "exit": result.returncode,
                            "stdout": result.stdout[-20000:],
                            "stderr": result.stderr[-4000:]})
    if check and result.returncode:
        raise RuntimeError(f"{name} exit {result.returncode}: {(result.stdout + result.stderr).strip()}")
    return result.stdout


def apply_link(report, link, label):
    command = "media-ctl -d /dev/media1 -l " + shlex.quote(link)
    run_step(report, label, command)


def restore_original(report, original):
    # A partial switch can leave any of the four links enabled. First clear
    # both sensor-to-CAMSV links, then sensor links, then rebuild original.
    for sensor in (2, 4):
        for link in reversed(ROUTES[sensor]):
            apply_link(report, link_descriptor(link, False), "rollback_disable")
    for link in ROUTES[original]:
        apply_link(report, link_descriptor(link, True), "rollback_enable")
    graph = run_step(report, "rollback_graph", "media-ctl -d /dev/media1 -p")
    if detect_route(graph) != original:
        raise RuntimeError("rollback graph does not match original route")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boot-id", required=True)
    parser.add_argument("--target-sensor", type=int, choices=(2, 4), required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--attended", action="store_true")
    args = parser.parse_args()
    if args.execute and not args.attended:
        parser.error("route changes require an attended trial")
    out = ROOT / "logs" / f"camera-route-switch-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"schema": 1, "boot_partition_writes": False,
              "stream_requested": False, "target_sensor": args.target_sensor,
              "directory": str(out), "steps": []}
    original = None
    changed = False
    try:
        boot = run_step(report, "boot_id", "cat /proc/sys/kernel/random/boot_id").strip()
        if boot != args.boot_id:
            raise RuntimeError("boot identity changed")
        health = json.loads(run_step(report, "health_before", "/usr/local/bin/lynx-status --assert-ready"))
        if health["issues"] or health["battery"]["capacity_percent"] < 25:
            raise RuntimeError("health or battery gate failed")
        if "mtk_cam_isp " not in run_step(report, "modules", "cat /proc/modules"):
            raise RuntimeError("ISP is not loaded")
        busy = run_step(report, "video_users", "fuser /dev/video145 2>/dev/null || true").strip()
        if busy:
            raise RuntimeError(f"capture device in use: {busy}")
        graph = run_step(report, "graph_before", "media-ctl -d /dev/media1 -p")
        original = detect_route(graph)
        report["original_sensor"] = original
        if original is None:
            raise RuntimeError("unrecognized or partial CAMSV route")
        if original == args.target_sensor:
            report["state"] = "already_selected"
        elif not args.execute:
            report["planned_links"] = plan_route(original, args.target_sensor)
            report["state"] = "plan_only"
        else:
            for index, link in enumerate(plan_route(original, args.target_sensor)):
                apply_link(report, link, f"link_{index}")
                changed = True
            graph = run_step(report, "graph_after", "media-ctl -d /dev/media1 -p")
            if detect_route(graph) != args.target_sensor:
                raise RuntimeError("target route verification failed")
            if run_step(report, "boot_id_after", "cat /proc/sys/kernel/random/boot_id").strip() != args.boot_id:
                raise RuntimeError("boot changed during route switch")
            json.loads(run_step(report, "health_after", "/usr/local/bin/lynx-status --assert-ready"))
            report["state"] = "route_selected_no_stream"
    except Exception as exc:
        report["state"] = "failed"
        report["error"] = str(exc)
        if changed and original is not None:
            try:
                if remote("cat /proc/sys/kernel/random/boot_id").stdout.strip() == args.boot_id:
                    restore_original(report, original)
                    report["state"] = "failed_original_route_restored"
            except Exception as rollback_exc:
                report["rollback_error"] = str(rollback_exc)
    finally:
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"], "receipt": str(out / "result.json"),
                      "error": report.get("error")}))
    if report["state"].startswith("failed"):
        sys.exit(1)


if __name__ == "__main__":
    main()
