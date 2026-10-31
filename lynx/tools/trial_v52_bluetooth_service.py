#!/usr/bin/env python3
"""Guarded same-boot OpenRC start, BLE PING/INFO, and STOP trial for Lynx V52."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
BOOT_SHA = "9206aafb339ad66b2d942ea5795b8f476a5eaf3a148f9cdfc76be22cb83e30bf"


def phone(command, timeout=10):
    argv = ssh_command("192.168.100.107", command)
    argv[-2:-2] = ["-p", "2222"]
    return subprocess.run(argv, capture_output=True, timeout=timeout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audible-smoke", action="store_true")
    parser.add_argument("--reconnect-smoke", action="store_true")
    parser.add_argument("--crash-recovery-smoke", action="store_true")
    args = parser.parse_args()
    receipt = ROOT / "logs" / f"v52-bluetooth-service-{time.time_ns()}"
    receipt.mkdir(mode=0o700)
    remote = "/run/lynx-bt-service-trial-" + str(time.time_ns())
    report = {"state": "preflight", "remote": remote,
              "started_at_utc": datetime.now(timezone.utc).isoformat(),
              "started_monotonic_ns": time.monotonic_ns(),
              "boot_partition_writes": False, "service_enabled": False,
              "paired": False, "steps": []}
    armed = False
    service_start_attempted = False

    def save():
        tmp = receipt / "result.tmp"
        tmp.write_text(json.dumps(report, indent=2) + "\n")
        tmp.replace(receipt / "result.json")

    def step(name, command, timeout=10):
        start = time.monotonic_ns()
        try:
            result = phone(command, timeout)
        except subprocess.TimeoutExpired as exc:
            (receipt / (name + ".stdout")).write_bytes(exc.stdout or b"")
            (receipt / (name + ".stderr")).write_bytes(exc.stderr or b"")
            report["steps"].append({"name": name, "timeout": True,
                                    "started_monotonic_ns": start,
                                    "ended_monotonic_ns": time.monotonic_ns()})
            save()
            raise RuntimeError(name + " timed out") from None
        (receipt / (name + ".stdout")).write_bytes(result.stdout)
        (receipt / (name + ".stderr")).write_bytes(result.stderr)
        report["steps"].append({"name": name, "exit": result.returncode,
                                "started_monotonic_ns": start,
                                "ended_monotonic_ns": time.monotonic_ns()})
        save()
        if result.returncode:
            raise RuntimeError(name + " failed")
        return result.stdout.decode(errors="replace")

    save()
    try:
        identity = step("identity", "cat /proc/sys/kernel/random/boot_id; "
                        "sha256sum /dev/sdc39 | cut -c1-64").splitlines()
        if len(identity) != 2 or identity[1] != BOOT_SHA:
            raise RuntimeError("boot_a differs from exact V52")
        report["boot_id"] = identity[0]
        health = json.loads(step("health_before", "/usr/local/bin/lynx-status --assert-ready"))
        if health["issues"] or health["battery"]["capacity_percent"] < 50 or \
                health["thermal"]["max_mC"] >= 45000:
            raise RuntimeError("power or Alpine health preflight failed")
        step("service_preflight", "set -eu; test -f /etc/init.d/lynx-bluetooth; "
             "test -S /run/lynx/noobd.sock; "
             "! rc-service lynx-bluetooth status >/dev/null 2>&1; "
             "! rc-service bluetooth status >/dev/null 2>&1; "
             "! rc-service dbus status >/dev/null 2>&1; "
             "! rc-update show default | grep -q lynx-bluetooth; "
             "test \"$(cat /sys/module/firmware_class/parameters/path)\" = /vendor/firmware")
        watchdog_seconds = 150 if args.crash_recovery_smoke else 90
        watchdog = ("#!/bin/sh\n"
                    f"sleep {watchdog_seconds}\n"
                    f"test -e {remote}/cancel && exit 0\n"
                    f"echo watchdog-reboot > {remote}/state\n"
                    "exec /sbin/reboot\n")
        wd_sha = __import__("hashlib").sha256(watchdog.encode()).hexdigest()
        step("watchdog_stage", f"mkdir -m 700 {remote}; "
             f"printf '%s' '{watchdog}' > {remote}/watchdog.sh; "
             f"chmod 700 {remote}/watchdog.sh; "
             f'test "$(sha256sum {remote}/watchdog.sh | cut -c1-64)" = {wd_sha}')
        armed = True
        step("watchdog_arm", f"/usr/bin/setsid /bin/sh {remote}/watchdog.sh "
             f"</dev/null >{remote}/watchdog.log 2>&1 & "
             f"echo $! > {remote}/pid; sleep 0.1; kill -0 $(cat {remote}/pid)")
        report["state"] = "watchdog-armed"
        save()
        service_start_attempted = True
        step("service_start", "rc-service lynx-bluetooth start", timeout=15)
        ready = False
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            result = phone("set -eu; test -f /run/lynx/bluetooth/ready; "
                           "rc-service lynx-bluetooth status >/dev/null 2>&1", timeout=5)
            if result.returncode == 0:
                ready = True
                break
            time.sleep(0.5)
        if not ready:
            raise RuntimeError("Bluetooth supervisor did not become ready")
        step("controller_ready", "set -eu; test -d /sys/class/bluetooth/hci0; "
             "bluetoothctl show | grep -q 'Powered: yes'; "
             "rc-service bluetooth status; rc-service dbus status")
        env = dict(os.environ, PYTHONPATH=str(ROOT / "tools/vendor_dbus_next") +
                   ":" + str(ROOT / "tools"))
        central = subprocess.run(["python3", str(ROOT / "tools/lynx_ble_nexus_ping.py"),
                                  "--factory-address-receipt",
                                  str(ROOT / "logs/v52-bt-factory-address-1793365780727214907.json"),
                                  "--audible-smoke" if args.audible_smoke else
                                  "--reconnect-smoke" if args.reconnect_smoke else "--vm-smoke",
                                  "--seconds", "25"],
                                 env=env, capture_output=True, timeout=32)
        (receipt / "nexus-gatt.stdout").write_bytes(central.stdout)
        (receipt / "nexus-gatt.stderr").write_bytes(central.stderr)
        report["nexus_ping"] = json.loads(central.stdout) if central.returncode == 0 else \
            {"exit": central.returncode}
        save()
        expected = ("audible-smoke-complete" if args.audible_smoke else
                    "reconnect-smoke-complete" if args.reconnect_smoke else
                    "vm-smoke-complete")
        if report["nexus_ping"].get("state") != expected:
            raise RuntimeError("authenticated BLE VM smoke test did not complete")
        if args.crash_recovery_smoke:
            process_query = ("set -e\n/usr/bin/python3 - <<'PY'\n"
                             "from pathlib import Path\n"
                             "matches=[]\n"
                             "for path in Path('/proc').glob('[0-9]*/cmdline'):\n"
                             " try: parts=path.read_bytes().split(b'\\0')\n"
                             " except OSError: continue\n"
                             " if parts[:4] == [b'/usr/bin/python3', "
                             "b'/usr/local/bin/lynx-ble-gatt', b'--seconds', b'0']:\n"
                             "  matches.append(int(path.parent.name))\n"
                             "assert len(matches)==1, matches\n"
                             "print(matches[0])\nPY")
            old_pid = int(step("gatt_pid_before", process_query).strip())
            step("inject_gatt_exit", f"kill -TERM {old_pid}")
            recovered = False
            deadline = time.monotonic() + 38
            while time.monotonic() < deadline:
                result = phone(process_query + "\ntest -f /run/lynx/bluetooth/ready; "
                               "rc-service lynx-bluetooth status >/dev/null 2>&1",
                               timeout=6)
                if result.returncode == 0:
                    try:
                        new_pid = int(result.stdout.decode().strip())
                    except ValueError:
                        new_pid = old_pid
                    if new_pid != old_pid:
                        recovered = True
                        report["gatt_pid_after"] = new_pid
                        break
                time.sleep(0.5)
            report["gatt_recovered"] = recovered
            save()
            if not recovered:
                raise RuntimeError("GATT child did not recover under OpenRC supervision")
            second = subprocess.run(
                ["python3", str(ROOT / "tools/lynx_ble_nexus_ping.py"),
                 "--factory-address-receipt",
                 str(ROOT / "logs/v52-bt-factory-address-1793365780727214907.json"),
                 "--reconnect-smoke", "--seconds", "25"],
                env=env, capture_output=True, timeout=32)
            (receipt / "nexus_after_recovery.stdout").write_bytes(second.stdout)
            (receipt / "nexus_after_recovery.stderr").write_bytes(second.stderr)
            report["nexus_after_recovery"] = (
                json.loads(second.stdout) if second.returncode == 0 else
                {"exit": second.returncode})
            save()
            if report["nexus_after_recovery"].get("state") != "reconnect-smoke-complete":
                raise RuntimeError("GATT recovery did not restore authenticated VM")
        report["state"] = "authenticated-vm-complete-awaiting-stop"
    except Exception as exc:
        report.update(state="failed", error=str(exc))
    finally:
        if service_start_attempted:
            try:
                result = phone("rc-service lynx-bluetooth stop", timeout=15)
                (receipt / "service_stop.stdout").write_bytes(result.stdout)
                (receipt / "service_stop.stderr").write_bytes(result.stderr)
                report["service_stop_exit"] = result.returncode
            except (OSError, subprocess.TimeoutExpired) as exc:
                report["service_stop_error"] = str(exc)
        try:
            cleaned = phone("set -eu; ! rc-service lynx-bluetooth status >/dev/null 2>&1; "
                            "! rc-service bluetooth status >/dev/null 2>&1; "
                            "! rc-service dbus status >/dev/null 2>&1; "
                            "test ! -d /sys/class/bluetooth/hci0; "
                            "test ! -e /run/lynx/bluetooth/factory-address; "
                            "test \"$(cat /sys/module/firmware_class/parameters/path)\" = /vendor/firmware",
                            timeout=10)
            report["teardown_verified"] = cleaned.returncode == 0
            (receipt / "teardown.stdout").write_bytes(cleaned.stdout)
            (receipt / "teardown.stderr").write_bytes(cleaned.stderr)
        except (OSError, subprocess.TimeoutExpired):
            report["teardown_verified"] = False
        try:
            state = phone("/usr/local/bin/lynx-status --assert-ready", timeout=10)
            after = json.loads(state.stdout)
            report["health_after"] = (state.returncode == 0 and not after["issues"] and
                                      after["boot_id"] == report.get("boot_id"))
        except (OSError, subprocess.TimeoutExpired, ValueError, KeyError):
            report["health_after"] = False
        if armed and report.get("teardown_verified") and report.get("health_after"):
            try:
                cancelled = phone(f"touch {remote}/cancel; test -e {remote}/cancel", timeout=8)
                report["watchdog_cancelled"] = cancelled.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                report["watchdog_cancelled"] = False
        if armed and not report.get("watchdog_cancelled"):
            report["watchdog_reboot_expected_within_seconds"] = watchdog_seconds
        if report["state"] == "authenticated-vm-complete-awaiting-stop" and \
                report.get("teardown_verified") and report.get("health_after") and \
                report.get("watchdog_cancelled"):
            report["state"] = "authenticated-vm-start-stop-healthy"
        report["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
        report["ended_monotonic_ns"] = time.monotonic_ns()
        save()
    print(json.dumps({"state": report["state"], "receipt": str(receipt / "result.json"),
                      "watchdog_cancelled": report.get("watchdog_cancelled"),
                      "error": report.get("error")}))
    if report["state"] != "authenticated-vm-start-stop-healthy":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
