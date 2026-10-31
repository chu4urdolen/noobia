#!/usr/bin/env python3
"""One guarded V52 reboot Bluetooth trial with automatic boot rollback."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
BOOT_SHA = "9206aafb339ad66b2d942ea5795b8f476a5eaf3a148f9cdfc76be22cb83e30bf"
GUARD = "lynx-bt-firstboot-guard"
GUARD_SCRIPT = r'''#!/sbin/openrc-run
description="One-shot Lynx Bluetooth first-boot rollback"
depend() {
    need localmount
    before lynx-bluetooth
}
start() {
    ebegin "Arming Lynx Bluetooth first-boot rollback"
    mkdir -p /run/lynx-bt-firstboot-guard
    /usr/bin/setsid /bin/sh -c '
        sleep 660
        test -e /run/lynx-bt-firstboot-guard/cancel && exit 0
        echo "Bluetooth first-boot trial timed out" >> /var/log/lynx-bt-firstboot-guard.log
        rc-update del lynx-bluetooth default
        rc-service lynx-bluetooth stop
        reboot
    ' </dev/null >>/var/log/lynx-bt-firstboot-guard.log 2>&1 &
    eend 0
}
'''


def phone(command, payload=None, timeout=12):
    argv = ssh_command("192.168.100.107", command)
    argv[-2:-2] = ["-p", "2222"]
    return subprocess.run(argv, input=payload, capture_output=True, timeout=timeout)


def main():
    receipt = ROOT / "logs" / f"v52-bluetooth-reboot-{time.time_ns()}"
    receipt.mkdir(mode=0o700)
    report = {"state": "preflight", "started_at_utc": datetime.now(timezone.utc).isoformat(),
              "partition_writes": False, "boot_guard_seconds": 660, "steps": []}

    def save():
        (receipt / "result.json").write_text(json.dumps(report, indent=2) + "\n")

    def step(name, command, payload=None, timeout=12):
        result = phone(command, payload, timeout)
        (receipt / (name + ".stdout")).write_bytes(result.stdout)
        (receipt / (name + ".stderr")).write_bytes(result.stderr)
        report["steps"].append({"name": name, "exit": result.returncode})
        save()
        if result.returncode:
            raise RuntimeError(name + " failed")
        return result.stdout.decode()

    save()
    guard_installed = False
    reboot_sent = False
    try:
        before = json.loads(step("health_before", "/usr/local/bin/lynx-status --assert-ready"))
        if before["issues"] or before["battery"]["capacity_percent"] < 70 or \
                before["thermal"]["max_mC"] >= 45000:
            raise RuntimeError("Alpine, battery, or temperature preflight failed")
        report["boot_id_before"] = before["boot_id"]
        step("identity", "set -eu; test \"$(sha256sum /dev/sdc39 | cut -c1-64)\" = "
             + BOOT_SHA + "; test -S /run/lynx/noobd.sock; "
             "! rc-service lynx-bluetooth status >/dev/null 2>&1; "
             "! rc-update show default | grep -q lynx-bluetooth; "
             "test ! -e /etc/init.d/" + GUARD)
        step("stage_guard", "set -eu; umask 077; cat > /etc/init.d/" + GUARD +
             "; chmod 755 /etc/init.d/" + GUARD +
             "; /bin/sh -n /etc/init.d/" + GUARD, GUARD_SCRIPT.encode())
        guard_installed = True
        step("enable_guard", "rc-update add " + GUARD + " default")
        step("enable_bluetooth", "rc-update add lynx-bluetooth default")
        report["state"] = "boot-guard-armed"
        save()
        try:
            result = phone("/sbin/reboot", timeout=4)
            report["reboot_exit"] = result.returncode
        except subprocess.TimeoutExpired:
            report["reboot_exit"] = "ssh-disconnected"
        reboot_sent = True
        deadline = time.monotonic() + 450
        while time.monotonic() < deadline:
            try:
                result = phone("cat /proc/sys/kernel/random/boot_id; "
                               "test -f /run/lynx/bluetooth/ready; "
                               "rc-service lynx-bluetooth status >/dev/null 2>&1; "
                               "/usr/local/bin/lynx-status --assert-ready", timeout=5)
                if result.returncode == 0:
                    lines = result.stdout.decode().splitlines()
                    if lines and lines[0] != report["boot_id_before"]:
                        report["boot_id_after"] = lines[0]
                        report["health_after"] = json.loads(lines[1])
                        break
            except (OSError, subprocess.TimeoutExpired, ValueError, IndexError):
                pass
            time.sleep(2)
        else:
            raise RuntimeError("Bluetooth or Alpine did not become ready after reboot")
        if report["health_after"]["issues"]:
            raise RuntimeError("Alpine health issues after reboot")
        report["state"] = "reboot-alpine-and-bluetooth-ready"
        save()
        env = dict(os.environ, PYTHONPATH=str(ROOT / "tools/vendor_dbus_next") +
                   ":" + str(ROOT / "tools"))
        central = subprocess.run(
            ["python3", str(ROOT / "tools/lynx_ble_nexus_ping.py"),
             "--factory-address-receipt",
             str(ROOT / "logs/v52-bt-factory-address-1793365780727214907.json"),
             "--reconnect-smoke", "--seconds", "25"],
            env=env, capture_output=True, timeout=32)
        (receipt / "nexus.stdout").write_bytes(central.stdout)
        (receipt / "nexus.stderr").write_bytes(central.stderr)
        report["nexus"] = (json.loads(central.stdout) if central.returncode == 0 else
                           {"exit": central.returncode})
        save()
        if report["nexus"].get("state") != "reconnect-smoke-complete":
            raise RuntimeError("reboot Bluetooth NRP/VM reconnect failed")
        step("stable", "set -eu; test -f /run/lynx/bluetooth/ready; "
             "rc-service lynx-bluetooth status >/dev/null 2>&1; "
             "test -d /sys/class/bluetooth/hci0; "
             "test \"$(cat /sys/module/firmware_class/parameters/path)\" = /vendor/firmware; "
             "/usr/local/bin/lynx-status --assert-ready")
        step("cancel_guard", "set -eu; touch /run/lynx-bt-firstboot-guard/cancel; "
             "rc-update del " + GUARD + " default; "
             "rm -f /etc/init.d/" + GUARD +
             "; test ! -e /etc/init.d/" + GUARD)
        report["state"] = "reboot-bluetooth-online-guard-cancelled"
    except Exception as exc:
        report.update(state="failed", error=str(exc))
        if guard_installed and not reboot_sent:
            try:
                step("rollback_enable", "rc-update del lynx-bluetooth default; "
                     "rc-update del " + GUARD + " default; rm -f /etc/init.d/" + GUARD)
            except (OSError, RuntimeError, subprocess.TimeoutExpired):
                pass
        elif reboot_sent:
            try:
                step("rollback_live", "set -eu; rc-update del lynx-bluetooth default; "
                     "rc-service lynx-bluetooth stop; "
                     "touch /run/lynx-bt-firstboot-guard/cancel; "
                     "rc-update del " + GUARD + " default; rm -f /etc/init.d/" + GUARD,
                     timeout=18)
                report["rollback_live"] = True
            except (OSError, RuntimeError, subprocess.TimeoutExpired):
                report["rollback_live"] = False
                report["automatic_rollback_expected_within_seconds"] = 660
    report["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
    save()
    print(json.dumps({"state": report["state"], "receipt": str(receipt / "result.json"),
                      "error": report.get("error")}))
    if report["state"] != "reboot-bluetooth-online-guard-cancelled":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
