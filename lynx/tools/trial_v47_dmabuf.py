#!/usr/bin/env python3
"""One bounded V47–V50 DMA-BUF display trial with durable host-side evidence.

The DRM program and stock display modules must already be staged. This tool
never writes boot partitions, never retries a modeset, and captures a reboot's
pstore before continuing diagnosis.
"""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
TARGETS = {
    "v47": ("192.168.100.8", "ebc6bb746aaf710d915c47036f92ce0c4ed23a185dfb5349b90e654bab7ba4ae"),
    "v48": ("192.168.100.7", "b560f233f5ecf838b5e948d0cd3685b676a84f3097adb00d2c8bfa6e5446ab1f"),
    "v49": ("192.168.100.7", "b560f233f5ecf838b5e948d0cd3685b676a84f3097adb00d2c8bfa6e5446ab1f"),
    "v50": ("192.168.100.107", "b560f233f5ecf838b5e948d0cd3685b676a84f3097adb00d2c8bfa6e5446ab1f"),
}
PROGRAM = "/var/lib/lynx-devroot/tmp/lynx_drm_dmabuf_pattern"
ATOMIC_PROGRAM = "/var/lib/lynx-devroot/tmp/lynx_drm_atomic_candidate"
ATOMIC_SHA = "0406aa15f90547d571271efdba5cd7566277dfb5e4e56f209c5c1f7e9d9271e5"
UI_PROGRAM = "/var/lib/lynx-devroot/tmp/lynx_drm_ui_candidate"
UI_SHA = "69b6e00947b3741e3adbdfc966df33f9cb5abc137a2b64e8631b0ed868a4ed70"


def ssh(ip, command, port=2222, timeout=20):
    argv = ssh_command(ip, command)
    argv[-2:-2] = ["-p", str(port)]
    try:
        run = subprocess.run(argv, capture_output=True, timeout=timeout)
        return {"exit": run.returncode, "stdout": run.stdout, "stderr": run.stderr}
    except subprocess.TimeoutExpired as exc:
        return {"exit": None, "timeout": True, "stdout": exc.stdout or b"",
                "stderr": exc.stderr or b""}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=TARGETS, default="v47")
    parser.add_argument("--no-live-trace", action="store_true",
                        help="use pstore and post-trial dmesg when /dev/kmsg streaming is unavailable")
    parser.add_argument("--atomic", action="store_true",
                        help="use the validated atomic primary-plane color-bar candidate")
    parser.add_argument("--ui", action="store_true",
                        help="V50 only: show the new Lynx status-screen candidate")
    parser.add_argument("--brightness", type=int, choices=range(1, 1001),
                        metavar="1..1000", help="set temporary panel brightness with atomic output")
    parser.add_argument("--show-seconds", type=int, choices=range(1, 16), metavar="1..15",
                        required=True)
    args = parser.parse_args()
    if args.atomic and args.ui:
        parser.error("--atomic and --ui are mutually exclusive")
    if args.atomic and args.target not in ("v49", "v50"):
        parser.error("--atomic requires --target v49 or v50")
    if args.ui and args.target != "v50":
        parser.error("--ui requires --target v50")
    if args.brightness is not None and not (args.atomic or args.ui):
        parser.error("--brightness requires --atomic or --ui")
    ip, init_sha = TARGETS[args.target]
    os.umask(0o077)
    out = ROOT / "logs" / f"{args.target}-dmabuf-trial-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "starting", "target": args.target, "atomic": args.atomic,
              "ui": args.ui,
              "temporary_brightness": args.brightness,
              "boot_partition_writes": False,
              "show_seconds": args.show_seconds, "steps": []}
    stream = None
    stream_out = None
    stream_err = None

    def step(name, command, port=2222, timeout=20):
        result = ssh(ip, command, port=port, timeout=timeout)
        (out / f"{name}.stdout").write_bytes(result.pop("stdout"))
        (out / f"{name}.stderr").write_bytes(result.pop("stderr"))
        result["name"] = name
        report["steps"].append(result)
        return result

    try:
        identity = step("identity", "cat /proc/sys/kernel/random/boot_id; uname -r; "
                        "sha256sum /init", port=22)
        lines = (out / "identity.stdout").read_text().splitlines()
        if identity["exit"] != 0 or len(lines) != 3 or \
           lines[1] != "5.10.149-android12-9-o-g311738fbb5a8" or \
           not lines[2].startswith(init_sha):
            raise RuntimeError("target is not the pinned rescue and kernel")
        boot_id = lines[0]
        report["boot_id"] = boot_id
        if args.target in ("v49", "v50"):
            v49 = step("v49_iommu_boot", "set -eu; "
                       "grep -q 'CHECKPOINT_MODULE_OK mtk_iommu.ko' /run/lynx/boot.log; "
                       "test -L /sys/bus/platform/devices/1e980000.gce/iommu_group", port=22)
            if v49["exit"] != 0:
                raise RuntimeError("V49 early IOMMU proof missing")
        preflight = step("preflight", "set -eu; "
                         f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{boot_id}"; '
                         "grep -q '^mtk_mml_mt6983 ' /proc/modules; "
                         "test -c /dev/dri/card0; "
                         "test \"$(cat /sys/class/drm/card0-DSI-1/status)\" = connected; "
                         "/usr/local/bin/lynx-status --assert-ready")
        if preflight["exit"] != 0:
            raise RuntimeError("display topology, card, or Alpine health preflight failed")
        health = json.loads((out / "preflight.stdout").read_text())
        trial_start_uptime = health["uptime_seconds"]
        charger = step("charger", "set -eu; "
                       "supply=/sys/class/power_supply/11e01000.i2c:mt6375@34:chg; "
                       "cat \"$supply/online\"; cat \"$supply/status\"")
        charger_lines = (out / "charger.stdout").read_text().splitlines()
        report["battery_percent"] = health["battery"]["capacity_percent"]
        report["thermal_max_mC"] = health["thermal"]["max_mC"]
        if health["battery"]["capacity_percent"] < 50 or \
           charger["exit"] != 0 or len(charger_lines) != 2 or \
           charger_lines[0] != "0" or \
           health["battery"]["temperature_mC"] >= 30000 or \
           health["thermal"]["max_mC"] >= 45000:
            raise RuntimeError("battery, charger, or temperature outside display trial guard")
        if args.atomic or args.ui:
            selected_program = UI_PROGRAM if args.ui else ATOMIC_PROGRAM
            selected_sha = UI_SHA if args.ui else ATOMIC_SHA
            atomic_preflight = step("atomic_binary", "set -eu; "
                                    f'test "$(sha256sum {selected_program} | cut -c1-64)" = "{selected_sha}"; '
                                    f"/bin/busybox timeout 12 {selected_program} --atomic-test")
            if atomic_preflight["exit"] != 0:
                raise RuntimeError("atomic candidate hash or test-only commit failed")
        if args.brightness is not None:
            brightness_preflight = step("brightness_preflight", "set -eu; "
                                        "node=/sys/kernel/oplus_display/oplus_brightness; "
                                        'test "$(cat "$node")" = 0; '
                                        f'test "$(cat /sys/kernel/oplus_display/oplus_max_brightness)" -ge {args.brightness}')
            if brightness_preflight["exit"] != 0:
                raise RuntimeError("panel brightness control not at safe baseline")
        # Keep a host-side kernel trace across a possible phone reboot. Pstore
        # can omit messages immediately before a BUG, including MMInfra errors.
        if not args.no_live_trace:
            stream_out = (out / "kmsg-live.stdout").open("wb")
            stream_err = (out / "kmsg-live.stderr").open("wb")
            stream_argv = ssh_command(ip, "cat /dev/kmsg")
            stream_argv[-2:-2] = ["-p", "22"]
            stream = subprocess.Popen(stream_argv, stdout=stream_out, stderr=stream_err)
            time.sleep(1)
            if stream.poll() is not None:
                raise RuntimeError("kernel message stream ended before modeset")
        # One CRTC modeset only. Capture both streams even if SSH drops.
        program = UI_PROGRAM if args.ui else (ATOMIC_PROGRAM if args.atomic else PROGRAM)
        mode = "--show-ui" if args.ui else ("--show-atomic" if args.atomic else "--show")
        if args.brightness is None:
            show_command = (f"/bin/busybox timeout {args.show_seconds + 10} " +
                            program + f" {mode} {args.show_seconds}")
        else:
            node = "/sys/kernel/oplus_display/oplus_brightness"
            work = f"/run/lynx/atomic-brightness-{time.time_ns()}"
            script = (
                "set -eu; "
                f"node={node}; test \"$(cat \"$node\")\" = 0; "
                f"work={work}; mkdir -p \"$work\"; : > \"$work/show.log\"; "
                f"({program} {mode} {args.show_seconds} > \"$work/show.log\" 2>&1) & pid=$!; "
                "ready=0; n=0; while [ $n -lt 40 ]; do "
                f"if grep -q \"displaying {'Lynx status' if args.ui else 'color bars'}\" \"$work/show.log\"; then ready=1; break; fi; "
                "kill -0 $pid 2>/dev/null || break; "
                "/bin/busybox sleep 0.1; n=$((n+1)); done; "
                "if [ \"$ready\" != 1 ]; then cat \"$work/show.log\"; wait $pid; exit 1; fi; "
                "trap \"printf %s 0 > $node\" EXIT; "
                f"printf %s {args.brightness} > \"$node\"; "
                "printf brightness_active=; cat \"$node\"; "
                "/bin/busybox sleep 5; printf %s 0 > \"$node\"; "
                "printf brightness_restored=; cat \"$node\"; "
                "wait $pid; cat \"$work/show.log\""
            )
            show_command = (f"/bin/busybox timeout {args.show_seconds + 12} "
                            f"/bin/sh -c '{script}'")
        display = step("show", show_command, timeout=args.show_seconds + 18)
        report["show_exit"] = display["exit"]
        report["show_timeout"] = display.get("timeout", False)
        after = step("after", "cat /proc/sys/kernel/random/boot_id; "
                     "/usr/local/bin/lynx-status --assert-ready", timeout=10)
        if after["exit"] == 0:
            ring = step("dmesg_after", "dmesg", timeout=25)
            if ring["exit"] == 0:
                errors = []
                for line in (out / "dmesg_after.stdout").read_text(errors="replace").splitlines():
                    stamp = re.match(r"\[\s*([0-9]+(?:\.[0-9]+)?)\]", line)
                    if stamp and float(stamp.group(1)) >= trial_start_uptime and \
                       ("cmdq timeout" in line.lower() or
                        "[cmdq][err]" in line.lower() or
                        "[disp][e]" in line.lower() or
                        "hre restore failed" in line.lower() or
                        "Unable to handle kernel" in line or
                        "Failed to power off domain mm_infra" in line):
                        errors.append(line[:250])
                report["kernel_display_errors"] = errors[:30]
            report["state"] = ("same-boot-with-display-errors" if
                               report.get("kernel_display_errors") else
                               "same-boot-no-detected-display-errors")
        else:
            report["state"] = "connection-lost-waiting-for-reboot"
            deadline = time.monotonic() + 300
            while time.monotonic() < deadline:
                probe = step("reboot-probe", "cat /proc/sys/kernel/random/boot_id", port=22,
                             timeout=8)
                if probe["exit"] == 0:
                    new_boot = (out / "reboot-probe.stdout").read_text().strip()
                    if new_boot != boot_id:
                        report["new_boot_id"] = new_boot
                        for name in ("console-ramoops-0", "pmsg-ramoops-0"):
                            step(name, f"cat /sys/fs/pstore/{name}", port=22, timeout=20)
                        report["state"] = "reboot-pstore-captured"
                        break
                time.sleep(10)
    except Exception as exc:
        report.update(state="stopped", error=str(exc))
    finally:
        if stream is not None and stream.poll() is None:
            stream.terminate()
            try:
                stream.wait(timeout=3)
            except subprocess.TimeoutExpired:
                stream.kill()
                stream.wait(timeout=3)
        if stream_out is not None:
            stream_out.close()
        if stream_err is not None:
            stream_err.close()
        report["live_kernel_trace_bytes"] = (out / "kmsg-live.stdout").stat().st_size if stream_out else 0
        report["finished_ns"] = time.time_ns()
        path = out / "result.json"
        path.write_text(json.dumps(report, indent=2) + "\n")
        print(path, flush=True)
    if report["state"] == "stopped":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
