#!/usr/bin/env python3
"""Start the staged V50 status display once, with a guarded cleanup path."""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
IP = "192.168.100.107"
PROGRAM = "/var/lib/lynx-devroot/tmp/lynx_drm_status_persistent"
PROGRAM_SHA = "1bab6b4e95949b46b160178945439b7ed2e1e370ce39da935918b1cd7a5027f8"
INIT_SHA = "b560f233f5ecf838b5e948d0cd3685b676a84f3097adb00d2c8bfa6e5446ab1f"
PID = "/run/lynx/status-display.pid"
LOG = "/run/lynx/status-display.log"
BRIGHTNESS = "/sys/kernel/oplus_display/oplus_brightness"


def ssh(command, *, port=2222, timeout=15):
    argv = ssh_command(IP, command)
    argv[-2:-2] = ["-p", str(port)]
    return subprocess.run(argv, capture_output=True, timeout=timeout)


def main():
    os.umask(0o077)
    out = ROOT / "logs" / f"v50-persistent-status-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "starting", "boot_partition_writes": False,
              "persistent_startup_enabled": False, "steps": []}
    started = False

    def step(name, command, *, port=2222, timeout=15):
        result = ssh(command, port=port, timeout=timeout)
        (out / f"{name}.stdout").write_bytes(result.stdout)
        (out / f"{name}.stderr").write_bytes(result.stderr)
        report["steps"].append({"name": name, "exit": result.returncode})
        if result.returncode:
            raise RuntimeError(f"{name} failed; inspect saved streams")
        return result.stdout.decode(errors="replace")

    def stop():
        ssh(f"printf 0 > {BRIGHTNESS}; "
            f"if test -s {PID}; then kill -TERM $(cat {PID}) 2>/dev/null || true; fi")

    try:
        identity = step("identity", "cat /proc/sys/kernel/random/boot_id; "
                        "uname -r; sha256sum /init | cut -c1-64", port=22).splitlines()
        if len(identity) != 3 or identity[1] != "5.10.149-android12-9-o-g311738fbb5a8" or identity[2] != INIT_SHA:
            raise RuntimeError("unexpected V50 rescue or kernel identity")
        report["boot_id"] = identity[0]
        health = json.loads(step("health", "/usr/local/bin/lynx-status --assert-ready"))
        if health["boot_id"] != identity[0] or health["battery"]["capacity_percent"] < 50 or \
           health["battery"]["temperature_mC"] >= 30000 or \
           health["thermal"]["max_mC"] >= 45000:
            raise RuntimeError("battery or thermal display guard failed")
        report["battery_percent"] = health["battery"]["capacity_percent"]
        report["trial_start_uptime"] = float(health["uptime_seconds"])
        pre = step("preflight", "set -eu; "
                   f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{identity[0]}"; '
                   "test -c /dev/dri/card0; "
                   f'test "$(sha256sum {PROGRAM} | cut -c1-64)" = "{PROGRAM_SHA}"; '
                   f'test "$(cat {BRIGHTNESS})" = 0; '
                   f'test ! -e {PID}; '
                   "supply=/sys/class/power_supply/11e01000.i2c:mt6375@34:chg; "
                   "cat \"$supply/online\"; cat \"$supply/status\"; cat \"$supply/usb_type\"")
        charger = pre.splitlines()
        if len(charger) != 3 or not (charger[0] == "0" or
                                     (charger[0] == "2" and charger[1] == "Charging" and
                                      "[DCP]" in charger[2])):
            raise RuntimeError("charger state changed")
        report["charger"] = charger
        started = True
        step("start", f"set -eu; : > {LOG}; "
             f"/bin/busybox nohup {PROGRAM} --show-ui-until-signal </dev/null >{LOG} 2>&1 & "
             f"echo $! > {PID}; sleep 1; kill -0 $(cat {PID})")
        ready = False
        for _ in range(30):
            state = step("ready", f"test -s {PID}; kill -0 $(cat {PID}); cat {LOG}")
            if "displaying Lynx status until signal" in state:
                ready = True
                break
            time.sleep(0.2)
        if not ready:
            raise RuntimeError("status program did not reach display commit")
        step("brightness", f"set -eu; printf 250 > {BRIGHTNESS}; "
             f'test "$(cat {BRIGHTNESS})" = 250')
        time.sleep(12)
        step("still_running", f"set -eu; kill -0 $(cat {PID}); "
             f'test "$(cat {BRIGHTNESS})" = 250; '
             "/usr/local/bin/lynx-status --assert-ready")
        ring = step("dmesg_after", "dmesg", timeout=30)
        errors = []
        for line in ring.splitlines():
            stamp = re.match(r"\[\s*([0-9]+(?:\.[0-9]+)?)\]", line)
            if stamp and float(stamp.group(1)) >= report["trial_start_uptime"] and \
               ("cmdq timeout" in line.lower() or "[cmdq][err]" in line.lower() or
                "Unable to handle kernel" in line):
                errors.append(line[:250])
        report["kernel_display_errors"] = errors[:20]
        if errors:
            raise RuntimeError("new kernel display errors; status display stopped")
        report["state"] = "running-on-current-boot"
    except Exception as exc:
        report.update(state="stopped-or-incomplete", error=str(exc))
        if started:
            stop()
    report["finished_ns"] = time.time_ns()
    path = out / "result.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"], "result": str(path)}))
    if report["state"] != "running-on-current-boot":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
