#!/usr/bin/env python3
"""Attempt one CAMSV Bayer frame with IRQ monitoring and a reboot fallback."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
STAGE = "/run/lynx/camera-camsv-trial"
FIRMWARE = ROOT / "linux-port/artifacts/stock-cph2493-August-eu-ota/wifi-reference/vendor-unpacked/firmware"
FIRMWARE_FILES = {
    # The stock CCU driver requests the dummy name. Stage the matching full
    # RISC-V ELF under that name for this RAM-only trial.
    "lib3a.ccu_dummy": ("lib3a.ccu", "6f8d51193a28c9279d403bda99e008f12af4f20add5d1154ee7f3523381ffdde"),
    "remoteproc_scp": ("remoteproc_scp", "66687aadf862bd776c8fc18b8e9f8e20089714856ee233b3902a591d0d5f2925"),
}
SENSOR_POWER_ISP_SHA = "0910503d465a9ea51b70a6b501fc7dead5f2eafd1f7d5a17845b1056eb5d9b3e"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attended", action="store_true", required=True)
    parser.add_argument("--boot-id", required=True)
    parser.add_argument("--exposure-lines", type=int,
                        help="bounded scalar exposure test; default is unchanged")
    parser.add_argument("--request-exposure-lines", type=int,
                        help="stage one scalar exposure control on the media request")
    parser.add_argument("--two-frame-request-exposure-lines", type=int,
                        help="stage exposure on the first request and capture two frames")
    parser.add_argument("--two-frame-request-raw-gain", type=int,
                        help="stage bounded vendor AE gain with the two-frame exposure request")
    args = parser.parse_args()
    if not args.attended:
        parser.error("Noob must be present for recovery")
    if args.exposure_lines is not None:
        parser.error("direct exposure S_CTRL blocked: both guarded trials lost CAMSV frames; see CAMERA-EXPOSURE-20261104.md")
    if args.request_exposure_lines is not None and not 1005 <= args.request_exposure_lines <= 1276:
        parser.error("request exposure must stay within the default frame period")
    if args.two_frame_request_exposure_lines is not None and not 1005 <= args.two_frame_request_exposure_lines <= 3000:
        parser.error("two-frame request exposure must be between 1005 and 3000")
    if args.request_exposure_lines is not None and args.two_frame_request_exposure_lines is not None:
        parser.error("choose one request exposure mode")
    if args.two_frame_request_raw_gain is not None:
        if args.two_frame_request_exposure_lines is None:
            parser.error("raw gain requires a two-frame exposure request")
        if not 1024 <= args.two_frame_request_raw_gain <= 4096:
            parser.error("raw gain must be between 1x and 4x")
    out = ROOT / "logs" / f"camera-camsv-frame-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"schema": 1, "boot_partition_writes": False, "steps": []}
    armed = False
    stream_attempted = False
    firmware_path_change_attempted = False
    pid = None
    monitors = []

    def save():
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")

    def step(name, command, timeout=25, check=True, data=None):
        argv = ssh_command("192.168.100.107", command)
        argv[-2:-2] = ["-p", "2222"]
        result = subprocess.run(argv, input=data, capture_output=True, timeout=timeout)
        (out / (name + ".stdout")).write_bytes(result.stdout)
        (out / (name + ".stderr")).write_bytes(result.stderr)
        report["steps"].append({"name": name, "exit": result.returncode,
                                "command": command, "unix_ns": time.time_ns()})
        save()
        if check and result.returncode:
            raise RuntimeError(f"{name} exited {result.returncode}")
        return result

    try:
        if step("boot_id", "cat /proc/sys/kernel/random/boot_id").stdout.decode().strip() != args.boot_id:
            raise RuntimeError("boot changed")
        matching_isp_receipts = []
        for path in (ROOT / "logs").glob("camera-isp-patched-trial-*/result.json"):
            try:
                prior = json.loads(path.read_text())
            except (OSError, ValueError):
                continue
            if (prior.get("boot_id") == args.boot_id and
                    prior.get("candidate_sha256") == SENSOR_POWER_ISP_SHA and
                    prior.get("state") == "stable_35_seconds_no_capture"):
                matching_isp_receipts.append(path)
        if not matching_isp_receipts:
            raise RuntimeError("no stable sensor-power ISP receipt for this boot")
        report["isp_receipt"] = str(max(matching_isp_receipts))
        if "mtk_cam_isp " not in step("module_before", "cat /proc/modules").stdout.decode():
            raise RuntimeError("sensor-power ISP module is not loaded")
        health = json.loads(step("health_before", "/usr/local/bin/lynx-status --assert-ready").stdout)
        if (health["issues"] or health["battery"]["capacity_percent"] < 35 or
                health["battery"]["temperature_mC"] >= 35000 or
                health["thermal"]["max_mC"] >= 45000):
            raise RuntimeError("health gate failed")
        graph = step("graph_before", "media-ctl -d /dev/media1 -p").stdout.decode()
        seninf = graph.split("entity 27: seninf-1", 1)[1].split("\n- entity ", 1)[0]
        if ('"sensor4":0 [ENABLED,DYNAMIC]' not in seninf or
                '"mtk-cam camsv-0":0 [ENABLED,DYNAMIC]' not in seninf or
                '"mtk-cam raw-0":0 [ENABLED,DYNAMIC]' in seninf):
            raise RuntimeError("CAMSV route is not exclusive")
        irq = step("irq_before", "grep cam_yuv_b /proc/interrupts").stdout.decode()
        if sum(int(x) for x in irq.split()[1:9]) > 1000:
            raise RuntimeError("YUV-B IRQ already high")
        step("stage", f"mkdir -p {STAGE}; chmod 700 {STAGE}")
        step("clear_old_frame", f"rm -f {STAGE}/sensor4.bayer")
        old_fw_path = step("firmware_path_before", "cat /sys/module/firmware_class/parameters/path").stdout.decode().strip()
        if old_fw_path != "/vendor/firmware":
            raise RuntimeError("unexpected global firmware path")
        step("firmware_dir", f"mkdir -p {STAGE}/fw; chmod 700 {STAGE}/fw")
        for name, (source_name, expected) in FIRMWARE_FILES.items():
            payload = (FIRMWARE / source_name).read_bytes()
            if hashlib.sha256(payload).hexdigest() != expected:
                raise RuntimeError(f"stock firmware checksum mismatch: {name}")
            step("stage_" + name.replace(".", "_"), f"cat > {STAGE}/fw/{name}", data=payload)
            actual = step("hash_" + name.replace(".", "_"), f"sha256sum {STAGE}/fw/{name}").stdout.decode().split()[0]
            if actual != expected:
                raise RuntimeError(f"staged firmware checksum mismatch: {name}")
        step("format", "v4l2-ctl -d /dev/video145 --set-fmt-video=width=1600,height=1200,pixelformat=BA81")
        fmt = step("format_verify", "v4l2-ctl -d /dev/video145 --get-fmt-video").stdout.decode()
        if "1600/1200" not in fmt or "'BA81'" not in fmt:
            raise RuntimeError("capture format not applied")
        watchdog = f"#!/bin/sh\nsleep 55\necho camsv-watchdog >> {STAGE}/watchdog.log\nreboot -f\n"
        argv = ssh_command("192.168.100.107", f"cat > {STAGE}/watchdog.sh")
        argv[-2:-2] = ["-p", "2222"]
        sent = subprocess.run(argv, input=watchdog.encode(), capture_output=True, timeout=10)
        if sent.returncode:
            raise RuntimeError("watchdog upload failed")
        step("watchdog_mode", f"chmod 700 {STAGE}/watchdog.sh")
        pid = step("watchdog_arm", f"setsid {STAGE}/watchdog.sh </dev/null >>{STAGE}/watchdog.log 2>&1 & echo $!").stdout.decode().strip()
        armed = True
        report["watchdog_pid"] = pid
        save()
        for label, script, extra in (
            ("kernel", "record_kernel_trial.py", ["--duration-seconds", "32"]),
            ("irq_health", "record_camera_health_window.py", ["--duration-seconds", "32", "--interval-seconds", "1"]),
        ):
            with (out / (label + ".monitor.stdout")).open("wb") as sink, (out / (label + ".monitor.stderr")).open("wb") as err:
                proc = subprocess.Popen([sys.executable, str(ROOT / "tools" / script), *extra],
                                        stdout=sink, stderr=err, start_new_session=True)
            monitors.append((label, proc))
        regulators = step("sensor_regulators", "for d in /sys/class/regulator/regulator.*; do "
                          "n=$(cat \"$d/name\" 2>/dev/null) || continue; "
                          "case \"$n\" in multi_reg_ldo4|multi_reg_ldo7) "
                          "printf '%s %s\\n' \"$n\" \"$d\";; esac; done").stdout.decode()
        regulator_paths = {}
        for line in regulators.splitlines():
            name, path = line.split()
            if name in regulator_paths:
                raise RuntimeError(f"duplicate regulator name: {name}")
            regulator_paths[name] = path
        if set(regulator_paths) != {"multi_reg_ldo4", "multi_reg_ldo7"}:
            raise RuntimeError(f"sensor regulators not uniquely identified: {regulators!r}")
        report["sensor_regulators"] = regulator_paths
        power_command = ("for i in $(seq 1 120); do "
                         "printf '%s ' \"$(date +%s%N)\"; "
                         f"cat {regulator_paths['multi_reg_ldo4']}/state "
                         f"{regulator_paths['multi_reg_ldo7']}/state 2>/dev/null | tr '\\n' ' '; "
                         "echo; sleep 0.1; done")
        power_argv = ssh_command("192.168.100.107", power_command)
        power_argv[-2:-2] = ["-p", "2222"]
        with (out / "sensor_power.monitor.stdout").open("wb") as sink, (out / "sensor_power.monitor.stderr").open("wb") as err:
            proc = subprocess.Popen(power_argv, stdout=sink, stderr=err, start_new_session=True)
        monitors.append(("sensor_power", proc))
        time.sleep(2)
        stopped = [label for label, proc in monitors if proc.poll() is not None]
        if "irq_health" in stopped or "sensor_power" in stopped:
            raise RuntimeError("required monitor stopped before stream: " + ",".join(stopped))
        if "kernel" in stopped:
            report["kernel_stream_early_exit"] = True
        firmware_path_change_attempted = True
        step("firmware_path_set", f"printf %s {STAGE}/fw > /sys/module/firmware_class/parameters/path")
        report["state"] = "stream_attempted"
        stream_attempted = True
        save()
        two_frame = args.two_frame_request_exposure_lines is not None
        if two_frame:
            helper = (ROOT / "tools/lynx_camsv_two_frame_capture.py").read_bytes()
            exposure_arg = f" --request-exposure-lines {args.two_frame_request_exposure_lines}"
            if args.two_frame_request_raw_gain is not None:
                exposure_arg += f" --request-raw-gain {args.two_frame_request_raw_gain}"
            remote_limit, host_limit = 25, 35
        else:
            helper = (ROOT / "tools/lynx_camsv_dmabuf_capture.py").read_bytes()
            exposure_arg = (f" --request-exposure-lines {args.request_exposure_lines}"
                            if args.request_exposure_lines is not None else "")
            remote_limit, host_limit = 18, 28
        capture = step("capture", f"/bin/busybox timeout -s KILL {remote_limit} python3 - --settle-ms 750{exposure_arg} --output {STAGE}/sensor4.bayer",
                       timeout=host_limit, check=False, data=helper)
        report["capture_exit"] = capture.returncode
        step("irq_after", "grep cam_yuv_b /proc/interrupts")
        health_after = step("health_after", "/usr/local/bin/lynx-status --assert-ready",
                            check=False)
        if health_after.returncode:
            # OpenRC service status can briefly race a supervisor restart.
            # Preserve both readings and fail if the issue persists.
            time.sleep(2)
            step("health_after_retry", "/usr/local/bin/lynx-status --assert-ready")
        step("frame_stat", f"stat -c '%s bytes' {STAGE}/sensor4.bayer", check=False)
        irq_after = (out / "irq_after.stdout").read_text()
        if sum(int(x) for x in irq_after.split()[1:9]) > 10000:
            raise RuntimeError("YUV-B IRQ storm")
        stat_words = (out / "frame_stat.stdout").read_text().split()
        frame_size = int(stat_words[0]) if stat_words else 0
        report["frame_bytes"] = frame_size
        capture_log = (out / "capture.stdout").read_text(errors="replace")
        try:
            helper_report = json.loads(capture_log.strip().splitlines()[-1])
        except (ValueError, IndexError):
            helper_report = {"state": "unparseable"}
        report["helper"] = helper_report
        step("firmware_path_restore", "printf %s /vendor/firmware > /sys/module/firmware_class/parameters/path")
        restored = step("firmware_path_verify", "cat /sys/module/firmware_class/parameters/path").stdout.decode().strip()
        if restored != old_fw_path:
            raise RuntimeError("global firmware path not restored")
        firmware_path_change_attempted = False
        step("watchdog_disarm", f"kill {pid} 2>/dev/null || true")
        armed = False
        report.pop("watchdog_pid", None)
        expected_state = "two_frames_captured" if two_frame else "frame_captured"
        if capture.returncode == 0 and frame_size >= 1600 * 1200 and helper_report.get("state") == expected_state:
            step("download_frame", f"cat {STAGE}/sensor4.bayer", timeout=20)
            if two_frame:
                step("download_first_frame", f"cat {STAGE}/sensor4-first.bayer", timeout=20)
            report["state"] = "frame_captured"
        else:
            report["state"] = "capture_failed_phone_healthy"
        if report["state"] == "frame_captured":
            decoded = subprocess.run([sys.executable, str(ROOT / "tools/decode_camera_bayer.py"),
                                      str(out / "download_frame.stdout"), "--output-dir", str(out)],
                                     capture_output=True, text=True, timeout=30)
            (out / "decode.stdout").write_text(decoded.stdout)
            (out / "decode.stderr").write_text(decoded.stderr)
            report["decode_exit"] = decoded.returncode
            if decoded.returncode == 0:
                stats = json.loads((out / "sensor4-frame-statistics.json").read_text())
                report["pixel_statistics"] = stats
                if stats["dominant_fraction"] >= 0.99:
                    report["state"] = "frame_buffer_captured_flat_scene_unverified"
            if two_frame:
                first_dir = out / "first-frame"
                first_dir.mkdir()
                first_decoded = subprocess.run([sys.executable, str(ROOT / "tools/decode_camera_bayer.py"),
                                                str(out / "download_first_frame.stdout"), "--output-dir", str(first_dir)],
                                               capture_output=True, text=True, timeout=30)
                (out / "decode_first.stdout").write_text(first_decoded.stdout)
                (out / "decode_first.stderr").write_text(first_decoded.stderr)
                report["decode_first_exit"] = first_decoded.returncode
                if first_decoded.returncode == 0:
                    report["first_pixel_statistics"] = json.loads((first_dir / "sensor4-frame-statistics.json").read_text())
    except Exception as exc:
        report["state"] = ("failed_watchdog_armed" if armed else
                           "failed_after_trial" if stream_attempted else "failed_before_trial")
        report["error"] = str(exc)
        if armed:
            try:
                current_boot = step("boot_id_on_error",
                                    "cat /proc/sys/kernel/random/boot_id").stdout.decode().strip()
                if current_boot != args.boot_id:
                    raise RuntimeError("boot changed during error cleanup")
                if firmware_path_change_attempted:
                    step("firmware_path_restore_on_error",
                         "printf %s /vendor/firmware > /sys/module/firmware_class/parameters/path")
                restored = step("firmware_path_verify_on_error",
                                "cat /sys/module/firmware_class/parameters/path").stdout.decode().strip()
                if restored != "/vendor/firmware":
                    raise RuntimeError("global firmware path not restored")
                step("health_on_error", "/usr/local/bin/lynx-status --assert-ready")
                step("watchdog_disarm_on_error", f"kill {pid} 2>/dev/null || true")
                armed = False
                report.pop("watchdog_pid", None)
                report["state"] = ("failed_after_trial_phone_healthy" if stream_attempted
                                   else "failed_before_trial")
            except Exception as cleanup_exc:
                report["cleanup_error"] = str(cleanup_exc)
    finally:
        for label, proc in monitors:
            try:
                proc.wait(timeout=12)
                report[label + "_monitor_exit"] = proc.returncode
            except subprocess.TimeoutExpired:
                report[label + "_monitor_still_running"] = True
        save()
    print(json.dumps({"state": report["state"], "receipt": str(out / "result.json"),
                      "error": report.get("error")}))
    if report["state"] not in ("frame_captured", "frame_buffer_captured_flat_scene_unverified",
                               "capture_failed_phone_healthy"):
        sys.exit(1)


if __name__ == "__main__":
    main()
