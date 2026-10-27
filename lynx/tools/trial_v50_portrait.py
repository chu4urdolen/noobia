#!/usr/bin/env python3
"""Bounded V50 portrait display trial; no boot write or service enable."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
IP = "192.168.100.107"
PID = "/run/lynx/portrait-trial.pid"
LOG = "/run/lynx/portrait-trial.log"
BIN = "/usr/local/bin/lynx-portrait-display"
BIN_SHA = "9aa4014a44366e6676d8493c65e0178cf4a6cb358e341d5a2d2302d8b3683c3d"
V50_SHA = "6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59"


def ssh(command, *, port=2222, timeout=25):
    argv = ssh_command(IP, command)
    argv[-2:-2] = ["-p", str(port)]
    return subprocess.run(argv, capture_output=True, timeout=timeout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stop", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    out = ROOT / "logs" / f"v50-portrait-trial-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "starting", "boot_partition_writes": False,
              "service_enabled": False, "steps": []}

    def step(name, command, *, port=2222, timeout=25):
        run = ssh(command, port=port, timeout=timeout)
        (out / f"{name}.stdout").write_bytes(run.stdout)
        (out / f"{name}.stderr").write_bytes(run.stderr)
        report["steps"].append({"name": name, "exit": run.returncode})
        if run.returncode:
            raise RuntimeError(f"{name} failed; inspect streams")
        return run.stdout.decode(errors="replace").strip()

    def stop():
        return step("stop", f"set -eu; printf 0 > /sys/kernel/oplus_display/oplus_brightness; "
                    f"if test -s {PID}; then kill -TERM $(cat {PID}) 2>/dev/null || true; fi; "
                    f"sleep 2; rm -f {PID}; /usr/local/bin/lynx-status --assert-ready >/dev/null")

    started = False
    try:
        identity = step("identity", "cat /proc/sys/kernel/random/boot_id; "
                        "uname -r; sha256sum /init | cut -c1-64; sha256sum /dev/sdc39 | cut -c1-64",
                        port=22).splitlines()
        if (len(identity) != 4 or identity[1] != "5.10.149-android12-9-o-g311738fbb5a8" or
            identity[2] != "b560f233f5ecf838b5e948d0cd3685b676a84f3097adb00d2c8bfa6e5446ab1f" or
            identity[3] != V50_SHA):
            raise RuntimeError("not the exact V50 rescue/kernel/boot_a")
        report["boot_id"] = identity[0]
        if args.stop:
            stop()
            report["state"] = "stopped"
        else:
            health = json.loads(step("health", "/usr/local/bin/lynx-status --assert-ready"))
            if (health["boot_id"] != identity[0] or
                health["battery"]["capacity_percent"] < 50 or
                health["battery"]["temperature_mC"] >= 30000 or
                health["thermal"]["max_mC"] >= 45000):
                raise RuntimeError("health or battery guard failed")
            uptime = float(step("uptime", "cut -d' ' -f1 /proc/uptime"))
            step("preflight", "set -eu; "
                 f'test "$(sha256sum {BIN} | cut -c1-64)" = {BIN_SHA}; '
                 "test -c /dev/dri/card0; test -c /dev/input/event0; "
                 "test \"$(cat /sys/class/input/input0/name)\" = touchpanel; "
                 f"test ! -e {PID}; test ! -e /run/lynx/display-auto.pid; "
                 "test ! -L /etc/runlevels/default/lynx-display; "
                 "test \"$(cat /sys/kernel/oplus_display/oplus_brightness)\" = 0")
            step("start", f"set -eu; : > {LOG}; "
                 f"/bin/busybox nohup {BIN} --show-portrait-touch-idle "
                 f"</dev/null >{LOG} 2>&1 & echo $! > {PID}; sleep 1; kill -0 $(cat {PID})")
            started = True
            ready = False
            for i in range(25):
                output = step(f"ready_{i:02d}", f"set -eu; kill -0 $(cat {PID}); cat {LOG}")
                if "displaying Lynx portrait with 10-second touch wake" in output:
                    ready = True
                    break
                time.sleep(0.2)
            if not ready:
                raise RuntimeError("portrait renderer did not reach modeset")
            time.sleep(14)
            after = step("after", f"set -eu; kill -0 $(cat {PID}); "
                         f"cat {LOG}; cat /sys/kernel/oplus_display/oplus_brightness; "
                         "/usr/local/bin/lynx-status --assert-ready", timeout=30)
            report["after"] = after[-2500:]
            ring = step("dmesg", "dmesg", timeout=30)
            errors = []
            for line in ring.splitlines():
                stamp = re.match(r"\[\s*([0-9]+(?:\.[0-9]+)?)\]", line)
                if stamp and float(stamp.group(1)) >= uptime and any(phrase in line.lower()
                    for phrase in ("cmdq timeout", "[cmdq][err]", "unable to handle kernel")):
                    errors.append(line[:250])
            report["kernel_errors"] = errors[:20]
            if errors:
                raise RuntimeError("kernel display error during portrait modeset")
            report["state"] = "renderer-running-awaiting-visual-confirmation"
    except Exception as exc:
        report.update(state="failed-or-stopped", error=str(exc))
        if started:
            try:
                stop()
            except Exception as stop_exc:
                report["stop_error"] = str(stop_exc)
    report["finished_ns"] = time.time_ns()
    receipt = out / "result.json"
    receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"], "result": str(receipt)}))
    if report["state"] == "failed-or-stopped":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
