#!/usr/bin/env python3
"""One guarded RAM trial of the locally patched Nord 3 ISP module."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "linux-port/camera-pipeline-modules.json"
KERNEL = "5.10.149-android12-9-o-g311738fbb5a8"
BOOT = "c047455271828cf9bfa90984eea121d8ede8754f6297fc06f33f1e99fb23c75e"
STAGE = "/run/lynx/camera-isp-irq-trial"
PATCHED_ISP = ROOT / "linux-port/artifacts/camera-yuv-irq-build/cam/mtk-cam-isp.ko"
PATCHED_SHA = "ade3ba24ff56d3b96f3f37842f878880d5e38a4da211e88768b4ebbd8d0cb5eb"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true",
                        help="load the ISP only after Noob is present for recovery")
    parser.add_argument("--attended", action="store_true",
                        help="confirm Noob is physically present for Fastboot recovery")
    args = parser.parse_args()
    if not args.execute or not args.attended:
        parser.error("--execute --attended required; Noob must be present for recovery")
    os.umask(0o077)
    out = ROOT / "logs" / f"camera-isp-patched-trial-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"schema": 1, "state": "preflight", "boot_partition_writes": False,
              "camera_capture_requested": False, "modules_unloaded": False,
              "steps": []}

    def save():
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")

    def step(name, command, data=None, timeout=20):
        argv = ssh_command("192.168.100.107", command)
        argv[-2:-2] = ["-p", "2222"]
        started = time.time_ns()
        result = subprocess.run(argv, input=data, capture_output=True, timeout=timeout)
        (out / (name + ".stdout")).write_bytes(result.stdout)
        (out / (name + ".stderr")).write_bytes(result.stderr)
        report["steps"].append({"name": name, "exit": result.returncode,
                                "started_unix_ns": started,
                                "finished_unix_ns": time.time_ns()})
        save()
        if result.returncode:
            raise RuntimeError(name + " failed; see receipt")
        return result.stdout.decode(errors="replace").strip()

    monitors = []
    armed = False
    load_attempted = False
    try:
        manifest = json.loads(MANIFEST.read_text())
        source = PATCHED_ISP
        payload = source.read_bytes()
        if manifest["kernel"] != KERNEL or hashlib.sha256(payload).hexdigest() != PATCHED_SHA:
            raise RuntimeError("patched ISP module incompatible")
        identity = step("identity", "cat /proc/sys/kernel/random/boot_id; uname -r; "
                        "sha256sum /dev/sdc39 | cut -c1-64", timeout=30).splitlines()
        if len(identity) != 3 or identity[1:] != [KERNEL, BOOT]:
            raise RuntimeError("unexpected Lynx boot")
        report["boot_id"] = identity[0]
        health = json.loads(step("health_before", "/usr/local/bin/lynx-status --assert-ready"))
        minimum = 25 if health["battery"]["current_mA_signed"] > 0 else 50
        if (health["boot_id"] != identity[0] or health["issues"] or
                health["battery"]["capacity_percent"] < minimum or
                health["battery"]["temperature_mC"] >= 35000 or
                health["thermal"]["max_mC"] >= 45000):
            raise RuntimeError("health gate failed")
        loaded = {line.split()[0] for line in step("modules_before", "cat /proc/modules").splitlines()}
        prefix = manifest["order"][:manifest["order"].index("mtk-cam-isp")]
        missing = [name for name in prefix if name.replace("-", "_") not in loaded]
        if missing:
            raise RuntimeError("camera prefix not loaded: " + ",".join(missing[:12]))
        if "mtk_cam_isp" in loaded:
            raise RuntimeError("ISP already loaded")
        if step("rcu_before", "dmesg | grep -E 'rcu_preempt detected stalls' | tail -3 || true"):
            raise RuntimeError("RCU stall exists before trial")
        step("stage_dir", f"mkdir -p {STAGE}; chmod 700 {STAGE}")
        remote = f"{STAGE}/mtk-cam-isp.ko"
        step("stage_module", f"cat > {remote}", payload, timeout=45)
        if step("hash_module", f"sha256sum {remote} | cut -c1-64") != PATCHED_SHA:
            raise RuntimeError("transferred ISP checksum mismatch")
        watchdog = f"{STAGE}/watchdog.sh"
        step("watchdog_file", f"cat > {watchdog}",
             b"#!/bin/sh\nsleep 65\necho camera-isp-patched-watchdog >> /run/lynx/camera-isp-irq-trial/watchdog.log\nreboot -f\n")
        step("watchdog_mode", f"chmod 700 {watchdog}")
        pid = step("watchdog_arm", f"setsid {watchdog} </dev/null "
                   f">>{STAGE}/watchdog.log 2>&1 & echo $!")
        report["watchdog_pid"] = pid
        armed = True
        save()
        for label, script, extra in (
            ("kernel", "record_kernel_trial.py", ["--duration-seconds", "45"]),
            ("irq_health", "record_camera_health_window.py",
             ["--duration-seconds", "45", "--interval-seconds", "1"])):
            sink = (out / (label + ".monitor.stdout")).open("wb")
            err = (out / (label + ".monitor.stderr")).open("wb")
            proc = subprocess.Popen([sys.executable, str(ROOT / "tools" / script), *extra],
                                    stdout=sink, stderr=err, start_new_session=True)
            sink.close()
            err.close()
            monitors.append((label, proc))
        time.sleep(3)
        if any(proc.poll() is not None for _, proc in monitors):
            raise RuntimeError("a monitor stopped before ISP load")
        report["state"] = "isp_load_started"
        save()
        load_attempted = True
        step("load_isp", f"/bin/busybox timeout 25 /sbin/insmod {remote}", timeout=32)
        report["state"] = "observing"
        save()
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            snapshot = step("observe_" + str(len(report["steps"])),
                            "cat /proc/interrupts | grep 'cam_yuv_b'; "
                            "echo __HEALTH__; /usr/local/bin/lynx-status --assert-ready",
                            timeout=10)
            irq_line, health_json = snapshot.split("__HEALTH__", 1)
            irq_parts = irq_line.split()
            if (len(irq_parts) < 9 or irq_parts[0] != "247:" or
                    sum(int(value) for value in irq_parts[1:9]) > 10000):
                raise RuntimeError("YUV-B IRQ count exceeded safe bound")
            after = json.loads(health_json.strip())
            if after["boot_id"] != identity[0] or after["issues"]:
                raise RuntimeError("Alpine health changed after ISP load")
            rcu = step("rcu_observe_" + str(len(report["steps"])),
                       "dmesg | grep -E 'rcu_preempt detected stalls' | tail -3 || true")
            if rcu:
                raise RuntimeError("RCU stall detected after ISP load")
            time.sleep(min(2, max(0, deadline - time.monotonic())))
        step("watchdog_disarm", f"kill {pid} 2>/dev/null || true")
        armed = False
        report.pop("watchdog_pid", None)
        report["state"] = "stable_35_seconds_no_capture"
    except Exception as exc:
        if armed and load_attempted and "YUV-B IRQ count" in str(exc):
            try:
                step("storm_reboot", "echo b > /proc/sysrq-trigger", timeout=6)
            except Exception as reboot_exc:
                report["storm_reboot_error"] = str(reboot_exc)
        if armed and not load_attempted:
            try:
                step("watchdog_disarm_before_load", f"kill {pid} 2>/dev/null || true")
                armed = False
                report.pop("watchdog_pid", None)
            except Exception as disarm_exc:
                report["disarm_error"] = str(disarm_exc)
        report.update(state="failed_watchdog_remains_armed" if armed else "failed_before_load",
                      error=str(exc))
    finally:
        for label, proc in monitors:
            try:
                proc.wait(timeout=25)
                report[label + "_monitor_exit"] = proc.returncode
            except subprocess.TimeoutExpired:
                report[label + "_monitor_still_running"] = True
        save()
    print(json.dumps({"state": report["state"], "receipt": str(out / "result.json"),
                      "error": report.get("error")}))
    if report["state"] != "stable_35_seconds_no_capture":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
