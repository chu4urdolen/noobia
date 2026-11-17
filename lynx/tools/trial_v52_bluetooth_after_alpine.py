#!/usr/bin/env python3
"""Start V52/V53 Bluetooth only after Alpine is healthy; never alter boot runlevels."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
V52_SHA = "9206aafb339ad66b2d942ea5795b8f476a5eaf3a148f9cdfc76be22cb83e30bf"
V53_SHA = "c047455271828cf9bfa90984eea121d8ede8754f6297fc06f33f1e99fb23c75e"
BOOT_SHAS = {"v52": V52_SHA, "v53": V53_SHA}
ADDRESS_RECEIPT = ROOT / "logs/v52-bt-factory-address-1793365780727214907.json"


def phone(command, timeout=12):
    argv = ssh_command("192.168.100.107", command)
    argv[-2:-2] = ["-p", "2222"]
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", action="store_true", help="run a bounded live trial")
    parser.add_argument("--candidate", choices=BOOT_SHAS, default="v52")
    parser.add_argument("--minutes", type=int, default=5)
    parser.add_argument("--leave-running", action="store_true",
                        help="keep radio on after a successful live trial")
    args = parser.parse_args()
    if not 1 <= args.minutes <= 15 or args.leave_running and not args.start:
        parser.error("minutes must be 1..15; --leave-running requires --start")
    os.umask(0o077)
    receipt = ROOT / "logs" / f"{args.candidate}-bt-after-alpine-{time.time_ns()}"
    receipt.mkdir(mode=0o700)
    report = {"state": "preflight", "partition_writes": False,
              "runlevel_writes": False, "radio_started": False, "steps": []}

    def save():
        (receipt / "result.json").write_text(json.dumps(report, indent=2) + "\n")

    def step(name, command, timeout=12, required=True):
        result = phone(command, timeout)
        (receipt / f"{name}.stdout").write_text(result.stdout)
        (receipt / f"{name}.stderr").write_text(result.stderr)
        report["steps"].append({"name": name, "exit": result.returncode})
        save()
        if required and result.returncode:
            raise RuntimeError(f"{name} failed")
        return result.stdout

    guard = "/run/lynx-bt-late-trial-" + str(time.time_ns())
    armed = started = False
    try:
        status = json.loads(step("health_before", "/usr/local/bin/lynx-status --assert-ready"))
        report["boot_id"] = status["boot_id"]
        if status["issues"] or status["battery"]["capacity_percent"] < 20 or \
                status["battery"]["temperature_mC"] >= 40000 or \
                status["thermal"]["max_mC"] >= 55000 or \
                status["uptime_seconds"] < 240:
            raise RuntimeError("Alpine, battery, thermal, or uptime gate failed")
        step("identity", "set -eu; test \"$(sha256sum /dev/sdc39 | cut -c1-64)\" = "
             + BOOT_SHAS[args.candidate] + "; test -S /run/lynx/noobd.sock; "
             "test ! -e /etc/lynx/bt-firstboot-trial; "
             "! rc-update show default | grep -q lynx-bluetooth; "
             "! rc-service lynx-bluetooth status >/dev/null 2>&1; "
             "rc-service lynx-wifi status >/dev/null; "
             "rc-service lynx-noobd status >/dev/null")
        if not args.start:
            report["state"] = "eligible-no-write"
            return
        watchdog_seconds = min(1200, args.minutes * 60 + 240)
        watchdog = ("#!/bin/sh\n" + f"sleep {watchdog_seconds}\n" +
                    f"test -e {guard}/cancel && exit 0\n" +
                    f"echo timeout > {guard}/state\nexec /sbin/openrc-shutdown -r now\n")
        digest = hashlib.sha256(watchdog.encode()).hexdigest()
        # The script is generated from numeric constants and a fixed /run path.
        step("stage_watchdog", "set -eu; mkdir -m 700 " + guard +
             "; cat > " + guard + "/watchdog.sh <<'LYNX_WATCHDOG'\n" +
             watchdog + "LYNX_WATCHDOG\nchmod 700 " + guard +
             f"/watchdog.sh; test \"$(sha256sum {guard}/watchdog.sh | cut -c1-64)\" = {digest}")
        step("arm_watchdog", "/usr/bin/setsid /bin/sh " + guard +
             "/watchdog.sh </dev/null >" + guard +
             "/watchdog.log 2>&1 & echo $! > " + guard +
             "/pid; sleep 0.1; kill -0 $(cat " + guard + "/pid)")
        armed = True
        started = True
        step("start", "rc-service lynx-bluetooth start", timeout=18)
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            if phone("test -f /run/lynx/bluetooth/ready; "
                     "rc-service lynx-bluetooth status >/dev/null 2>&1", 6).returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("Bluetooth did not become ready")
        report["radio_started"] = True
        save()
        env = dict(os.environ, PYTHONPATH=str(ROOT / "tools/vendor_dbus_next") +
                   ":" + str(ROOT / "tools"))
        central = subprocess.run(
            ["python3", str(ROOT / "tools/lynx_ble_nexus_ping.py"),
             "--factory-address-receipt", str(ADDRESS_RECEIPT),
             "--reconnect-smoke", "--seconds", "40"],
            env=env, capture_output=True, text=True, timeout=85)
        (receipt / "nexus.stdout").write_text(central.stdout)
        (receipt / "nexus.stderr").write_text(central.stderr)
        report["nexus"] = json.loads(central.stdout) if central.returncode == 0 else \
            {"exit": central.returncode}
        save()
        if report["nexus"].get("state") != "reconnect-smoke-complete":
            raise RuntimeError("authenticated BLE reconnect failed")
        until = time.monotonic() + args.minutes * 60
        while time.monotonic() < until:
            current = json.loads(step("health_sample_" + str(len(report["steps"])),
                                      "set -eu; test -f /run/lynx/bluetooth/ready; "
                                      "rc-service lynx-bluetooth status >/dev/null; "
                                      "/usr/local/bin/lynx-status --assert-ready"))
            if current["boot_id"] != report["boot_id"] or current["issues"] or \
                    current["battery"]["capacity_percent"] < 15 or \
                    current["thermal"]["max_mC"] >= 55000:
                raise RuntimeError("sustained health check failed")
            time.sleep(min(30, max(0, until - time.monotonic())))
        report["state"] = "sustained-healthy"
    except Exception as exc:
        report.update(state="failed", error=str(exc))
    finally:
        safe_to_cancel = not started or (report["state"] == "sustained-healthy" and
                                         args.leave_running)
        if started and (report["state"] != "sustained-healthy" or not args.leave_running):
            try:
                step("stop", "rc-service lynx-bluetooth stop", timeout=20, required=False)
                step("stopped_check", "set -eu; "
                     "! rc-service lynx-bluetooth status >/dev/null 2>&1; "
                     "test ! -d /sys/class/bluetooth/hci0; "
                     "/usr/local/bin/lynx-status --assert-ready")
                safe_to_cancel = True
            except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
                report["stop_error"] = str(exc)
                report["state"] = "failed"
        if armed and safe_to_cancel:
            try:
                step("cancel_watchdog", "touch " + guard +
                     "/cancel; test -e " + guard + "/cancel")
            except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
                report["watchdog_error"] = str(exc)
                report["state"] = "failed"
        elif armed:
            report["watchdog_remains_armed"] = True
        if report["state"] == "sustained-healthy":
            report["state"] = "running-after-healthy-trial" if args.leave_running else \
                              "stopped-after-healthy-trial"
        save()
        print(json.dumps({"state": report["state"],
                          "receipt": str(receipt / "result.json"),
                          "error": report.get("error")}))
    if report["state"] not in ("eligible-no-write", "running-after-healthy-trial",
                               "stopped-after-healthy-trial"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
