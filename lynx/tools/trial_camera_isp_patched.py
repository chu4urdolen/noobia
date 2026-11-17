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
PATCHED_ISP = ROOT / "linux-port/artifacts/camera-yuv-irq-build/cam/mtk-cam-isp-stripped.ko"
PATCHED_SHA = "b0072fce10d91202cf02586bb21cea7ccb61d36988828fc86c696e8f9c838b64"
PATCH = ROOT / "linux-port/patches/camera-yuv-irq/0001-gate-yuv-irq-on-runtime-power.patch"
PATCH_SHA = "31f6176bdb69951552c4a6b09653415217f1312d4981574d2d80d735f67fb7cb"
BUILD_RECEIPT = ROOT / "linux-port/artifacts/camera-yuv-irq-build/build-result.json"
SENSOR_POWER_PATCH = ROOT / "linux-port/patches/camera-yuv-irq/0002-power-sensor-for-camsv.patch"
SENSOR_POWER_PATCH_SHA = "35931ce25dac39d5ab77bd771a082c242a61367b52b91673ca888815ddea8418"
SENSOR_POWER_BUILD = ROOT / "linux-port/artifacts/camera-yuv-irq-rebuild-1793787441973056494/build-result.json"
SENSOR_POWER_ISP = ROOT / "linux-port/artifacts/camera-yuv-irq-rebuild-1793787441973056494/cam/mtk-cam-isp-stripped.ko"
SENSOR_POWER_SHA = "0910503d465a9ea51b70a6b501fc7dead5f2eafd1f7d5a17845b1056eb5d9b3e"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--execute", action="store_true",
                      help="load the ISP only after Noob is present for recovery")
    mode.add_argument("--preflight-only", action="store_true",
                      help="check local artifact and Lynx read-only; do not load anything")
    parser.add_argument("--attended", action="store_true",
                        help="confirm Noob is physically present for Fastboot recovery")
    parser.add_argument("--with-sensor-power", action="store_true",
                        help="trial the CAMSV sensor-power patch in addition to the YUV IRQ gate")
    args = parser.parse_args()
    if args.execute and not args.attended:
        parser.error("--execute --attended required; Noob must be present for recovery")
    candidate = SENSOR_POWER_ISP if args.with_sensor_power else PATCHED_ISP
    candidate_sha = SENSOR_POWER_SHA if args.with_sensor_power else PATCHED_SHA
    build_receipt = SENSOR_POWER_BUILD if args.with_sensor_power else BUILD_RECEIPT
    os.umask(0o077)
    out = ROOT / "logs" / f"camera-isp-patched-trial-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"schema": 1, "state": "preflight", "boot_partition_writes": False,
              "camera_capture_requested": False, "modules_unloaded": False,
              "candidate_sha256": candidate_sha, "patch_sha256": PATCH_SHA,
              "sensor_power_patch": args.with_sensor_power,
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
        source = candidate
        payload = source.read_bytes()
        if manifest["kernel"] != KERNEL or hashlib.sha256(payload).hexdigest() != candidate_sha:
            raise RuntimeError("patched ISP module incompatible")
        if hashlib.sha256(PATCH.read_bytes()).hexdigest() != PATCH_SHA:
            raise RuntimeError("source patch changed since module build")
        if args.with_sensor_power and hashlib.sha256(SENSOR_POWER_PATCH.read_bytes()).hexdigest() != SENSOR_POWER_PATCH_SHA:
            raise RuntimeError("sensor-power source patch changed since module build")
        build = json.loads(build_receipt.read_text())
        if (build.get("state") != "offline-module-built-not-tested-on-lynx" or
                build.get("stripped_trial_module_sha256") != candidate_sha):
            raise RuntimeError("patched ISP build receipt incomplete")
        if args.with_sensor_power and build.get("extra_patch_sha256") != SENSOR_POWER_PATCH_SHA:
            raise RuntimeError("sensor-power build receipt mismatch")
        if args.with_sensor_power:
            if (build.get("import_count") != 322 or len(build.get("depends", [])) != 16 or
                    not build.get("vermagic", "").startswith(KERNEL)):
                raise RuntimeError("sensor-power module ABI receipt incomplete")
        elif not build.get("import_crcs_equal") or not build.get("depends_equal"):
            raise RuntimeError("YUV-only module ABI receipt incomplete")
        identity = step("identity", "cat /proc/sys/kernel/random/boot_id; uname -r; "
                        "sha256sum /dev/sdc39 | cut -c1-64", timeout=30).splitlines()
        if len(identity) != 3 or identity[1:] != [KERNEL, BOOT]:
            raise RuntimeError("unexpected Lynx boot")
        report["boot_id"] = identity[0]
        health = json.loads(step("health_before", "/usr/local/bin/lynx-status --assert-ready"))
        minimum = 25 if health["battery"]["current_mA_signed"] > 0 else 35
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
        if args.preflight_only:
            report["state"] = "read_only_preflight_passed"
            save()
            print(json.dumps({"state": report["state"],
                              "receipt": str(out / "result.json"), "error": None}))
            return
        step("stage_dir", f"mkdir -p {STAGE}; chmod 700 {STAGE}")
        remote = f"{STAGE}/mtk-cam-isp.ko"
        step("stage_module", f"cat > {remote}", payload, timeout=45)
        if step("hash_module", f"sha256sum {remote} | cut -c1-64") != candidate_sha:
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
            if (len(irq_parts) < 9 or not irq_parts[0].rstrip(":").isdigit()
                    or "cam_yuv_b" not in irq_line):
                raise RuntimeError("YUV-B IRQ line missing")
            if sum(int(value) for value in irq_parts[1:9]) > 10000:
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
        elif armed and load_attempted:
            try:
                snapshot = step("post_error_safety_check",
                                "grep cam_yuv_b /proc/interrupts; echo __HEALTH__; "
                                "/usr/local/bin/lynx-status --assert-ready; echo __RCU__; "
                                "dmesg | grep -E 'rcu_preempt detected stalls' | tail -3 || true",
                                timeout=10)
                irq_line, rest = snapshot.split("__HEALTH__", 1)
                health_text, rcu_text = rest.split("__RCU__", 1)
                parts = irq_line.split()
                health = json.loads(health_text)
                if (len(parts) < 9 or "cam_yuv_b" not in irq_line or
                        sum(int(value) for value in parts[1:9]) > 10000 or
                        health["boot_id"] != identity[0] or health["issues"] or
                        rcu_text.strip()):
                    raise RuntimeError("post-error safety gate failed")
                step("watchdog_disarm_after_safe_error", f"kill {pid} 2>/dev/null || true")
                armed = False
                report.pop("watchdog_pid", None)
                report["post_error_safe_check"] = True
            except Exception as safety_exc:
                report["post_error_safety_error"] = str(safety_exc)
        if armed and not load_attempted:
            try:
                step("watchdog_disarm_before_load", f"kill {pid} 2>/dev/null || true")
                armed = False
                report.pop("watchdog_pid", None)
            except Exception as disarm_exc:
                report["disarm_error"] = str(disarm_exc)
        report.update(state="failed_watchdog_remains_armed" if armed else
                      "failed_after_safe_check" if load_attempted else "failed_before_load",
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
