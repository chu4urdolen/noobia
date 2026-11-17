#!/usr/bin/env python3
"""Switch one V50 boot from the static status UI to 10-second touch idle."""

import json
import os
from pathlib import Path
import re
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
IP = "192.168.100.107"
BOOT = "2f55a194-dfd7-4664-b4cb-9d2275cc947c"
INIT_SHA = "b560f233f5ecf838b5e948d0cd3685b676a84f3097adb00d2c8bfa6e5446ab1f"
NEW = "/var/lib/lynx-devroot/tmp/lynx_drm_status_touch_idle"
NEW_SHA = "1a3d21bd40f5903377b800d0bb085443c0653a8c5ff30e1abb964e5eab0e2387"
OLD_PID = "/run/lynx/status-display.pid"
PID = "/run/lynx/status-touch.pid"
LOG = "/run/lynx/status-touch.log"
BRIGHTNESS = "/sys/kernel/oplus_display/oplus_brightness"


def ssh(command, *, port=2222, timeout=20):
    argv = ssh_command(IP, command)
    argv[-2:-2] = ["-p", str(port)]
    return subprocess.run(argv, capture_output=True, timeout=timeout)


def main():
    os.umask(0o077)
    out = ROOT / "logs" / f"v50-touch-idle-trial-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "starting", "boot_partition_writes": False,
              "new_program_sha256": NEW_SHA, "steps": []}
    started = False

    def step(name, command, *, port=2222, timeout=20):
        result = ssh(command, port=port, timeout=timeout)
        (out / f"{name}.stdout").write_bytes(result.stdout)
        (out / f"{name}.stderr").write_bytes(result.stderr)
        report["steps"].append({"name": name, "exit": result.returncode})
        if result.returncode:
            raise RuntimeError(f"{name} failed; inspect saved streams")
        return result.stdout.decode(errors="replace")

    try:
        identity = step("identity", "cat /proc/sys/kernel/random/boot_id; "
                        "uname -r; sha256sum /init | cut -c1-64", port=22).splitlines()
        if identity != [BOOT, "5.10.149-android12-9-o-g311738fbb5a8", INIT_SHA]:
            raise RuntimeError("boot identity changed")
        health = json.loads(step("health", "/usr/local/bin/lynx-status --assert-ready"))
        if health["boot_id"] != BOOT or health["battery"]["capacity_percent"] < 50 or \
           health["battery"]["temperature_mC"] >= 30000 or \
           health["thermal"]["max_mC"] >= 45000:
            raise RuntimeError("health guard failed")
        report["trial_start_uptime"] = float(health["uptime_seconds"])
        step("preflight", "set -eu; "
             f'test "$(sha256sum {NEW} | cut -c1-64)" = "{NEW_SHA}"; '
             "test \"$(cat /sys/class/input/input0/name)\" = touchpanel; "
             "test -c /dev/input/event0; "
             f"test -s {OLD_PID}; kill -0 $(cat {OLD_PID}); test ! -e {PID}; "
             f'test "$(cat {BRIGHTNESS})" = 250')
        step("stop_old", f"set -eu; printf 0 > {BRIGHTNESS}; "
             f"kill -TERM $(cat {OLD_PID}); sleep 2; "
             f"! kill -0 $(cat {OLD_PID}) 2>/dev/null || "
             f"test \"$(cat /proc/$(cat {OLD_PID})/stat | cut -d' ' -f3)\" = Z; "
             f"rm -f {OLD_PID}; test \"$(cat {BRIGHTNESS})\" = 0")
        started = True
        step("start_new", f"set -eu; : > {LOG}; "
             f"/bin/busybox nohup {NEW} --show-ui-touch-idle </dev/null >{LOG} 2>&1 & "
             f"echo $! > {PID}; sleep 1; kill -0 $(cat {PID})")
        ready = False
        for _ in range(25):
            text = step("ready", f"set -eu; kill -0 $(cat {PID}); cat {LOG}")
            if "displaying Lynx status with 10-second touch wake" in text:
                ready = True
                break
            time.sleep(0.2)
        if not ready:
            raise RuntimeError("new status program did not reach display commit")
        step("lit", f"set -eu; test \"$(cat {BRIGHTNESS})\" = 250; "
             "/usr/local/bin/lynx-status --assert-ready >/dev/null")
        time.sleep(12)
        step("dark", f"set -eu; kill -0 $(cat {PID}); "
             f'test "$(cat {BRIGHTNESS})" = 0; '
             f"grep -q idle_dark {LOG}; "
             "/usr/local/bin/lynx-status --assert-ready >/dev/null")
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
            raise RuntimeError("new display kernel error; stop trial")
        report["state"] = "dark-awaiting-human-touch"
    except Exception as exc:
        report.update(state="stopped-or-incomplete", error=str(exc))
        if started:
            ssh(f"printf 0 > {BRIGHTNESS}; "
                f"if test -s {PID}; then kill -TERM $(cat {PID}) 2>/dev/null || true; fi")
    report["finished_ns"] = time.time_ns()
    path = out / "result.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"], "result": str(path)}))
    if report["state"] != "dark-awaiting-human-touch":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
