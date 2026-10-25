#!/usr/bin/env python3
"""One bounded V47/V48 DMA-BUF display trial with durable host-side evidence.

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
}
PROGRAM = "/var/lib/lynx-devroot/tmp/lynx_drm_dmabuf_pattern"


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
    parser.add_argument("--show-seconds", type=int, choices=range(1, 16), metavar="1..15",
                        required=True)
    args = parser.parse_args()
    ip, init_sha = TARGETS[args.target]
    os.umask(0o077)
    out = ROOT / "logs" / f"{args.target}-dmabuf-trial-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "starting", "target": args.target,
              "boot_partition_writes": False,
              "show_seconds": args.show_seconds, "steps": []}

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
        # One CRTC modeset only. Capture both streams even if SSH drops.
        display = step("show", "/bin/busybox timeout 12 " + PROGRAM +
                       f" --show {args.show_seconds}", timeout=20)
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
        report["finished_ns"] = time.time_ns()
        path = out / "result.json"
        path.write_text(json.dumps(report, indent=2) + "\n")
        print(path, flush=True)
    if report["state"] == "stopped":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
