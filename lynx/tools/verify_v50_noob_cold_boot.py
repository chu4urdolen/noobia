#!/usr/bin/env python3
"""One guarded V50 cold-boot check for Lynx's Noob and haptic services."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
IMAGE = ROOT / "linux-port/artifacts/static-noobia-ip-v50-offline/nord3-static-noobia-ip-v50-untested.img"
IMAGE_SHA = "6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59"
INIT_SHA = "b560f233f5ecf838b5e948d0cd3685b676a84f3097adb00d2c8bfa6e5446ab1f"
KERNEL = "5.10.149-android12-9-o-g311738fbb5a8"
IP = "192.168.100.107"


def ssh(command, timeout=12, port=2222):
    args = ssh_command(IP, command)
    args[-2:-2] = ["-p", str(port)]
    return subprocess.run(args, capture_output=True, timeout=timeout)


def main():
    out = ROOT / "logs" / f"v50-noob-cold-boot-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "preflight", "boot_partition_writes": False,
              "steps": [], "reboot_sent": False}

    def save():
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")

    def step(label, command, *, accept_disconnect=False, timeout=12, port=2222):
        result = ssh(command, timeout=timeout, port=port)
        (out / f"{label}.stdout").write_bytes(result.stdout)
        (out / f"{label}.stderr").write_bytes(result.stderr)
        report["steps"].append({"name": label, "exit": result.returncode})
        save()
        if result.returncode and not accept_disconnect:
            raise RuntimeError(f"{label} failed; see saved streams")
        return result.stdout.decode(errors="replace")

    try:
        if hashlib.sha256(IMAGE.read_bytes()).hexdigest() != IMAGE_SHA:
            raise RuntimeError("V50 rollback image hash mismatch")
        old = step("identity_before",
                   "cat /proc/sys/kernel/random/boot_id; uname -r; "
                   "sha256sum /init /dev/sdc39 | cut -c1-64",
                   timeout=25, port=22).splitlines()
        if len(old) != 4 or old[1:] != [KERNEL, INIT_SHA, IMAGE_SHA]:
            raise RuntimeError("current boot is not pinned V50")
        report["old_boot_id"] = old[0]
        health = json.loads(step("health_before", "/usr/local/bin/lynx-status --assert-ready"))
        if (health["boot_id"] != old[0] or
            health["battery"]["capacity_percent"] < 50 or
            health["battery"]["temperature_mC"] >= 35000 or
            health["thermal"]["max_mC"] >= 45000):
            raise RuntimeError("health guard refused reboot")
        report["battery_percent_before"] = health["battery"]["capacity_percent"]
        step("services_before", "set -eu; "
             "for name in lynx-display lynx-media lynx-haptic lynx-noobd; do "
             'rc-service "$name" status; test -L "/etc/runlevels/default/$name"; done; '
             'test "$(cat /sys/class/leds/vibrator/oplus_activate)" = 0; '
             "/sbin/openrc-shutdown -D -r now")
        step("reboot_request", "/sbin/openrc-shutdown -r now",
             accept_disconnect=True, timeout=12)
        report["reboot_sent"] = True
        report["state"] = "awaiting-new-boot"
        save()
        print("reboot sent; watching Lynx for a new boot", flush=True)
        deadline = time.monotonic() + 600
        attempt = 0
        new_id = None
        while time.monotonic() < deadline:
            attempt += 1
            try:
                result = ssh("cat /proc/sys/kernel/random/boot_id", timeout=8)
            except subprocess.TimeoutExpired:
                result = None
            if result and result.returncode == 0:
                boot_id = result.stdout.decode(errors="replace").strip()
                if boot_id and boot_id != old[0]:
                    new_id = boot_id
                    break
            if attempt % 10 == 0:
                print(f"watch attempt {attempt}: awaiting new Alpine SSH", flush=True)
            time.sleep(3)
        if not new_id:
            raise RuntimeError("new Alpine SSH boot not observed within 600 seconds")
        report["new_boot_id"] = new_id
        print(f"new boot: {new_id}", flush=True)
        # OpenRC may still be starting display, so wait for all services.
        ready_deadline = time.monotonic() + 180
        while time.monotonic() < ready_deadline:
            try:
                health_result = ssh("/usr/local/bin/lynx-status --assert-ready", timeout=12)
                services_result = ssh("set -eu; for name in lynx-display lynx-media "
                                      'lynx-haptic lynx-noobd; do rc-service "$name" status; done',
                                      timeout=12)
            except subprocess.TimeoutExpired:
                time.sleep(3)
                continue
            if health_result.returncode == 0 and services_result.returncode == 0:
                break
            time.sleep(3)
        else:
            raise RuntimeError("core or new OpenRC services did not become ready")
        (out / "health_after.stdout").write_bytes(health_result.stdout)
        (out / "services_after.stdout").write_bytes(services_result.stdout)
        report["steps"].append({"name": "health_after", "exit": health_result.returncode})
        report["steps"].append({"name": "services_after", "exit": services_result.returncode})
        after = step("identity_after", "cat /proc/sys/kernel/random/boot_id; "
                     "uname -r; sha256sum /init /dev/sdc39 | cut -c1-64",
                     timeout=25, port=22).splitlines()
        if after != [new_id, KERNEL, INIT_SHA, IMAGE_SHA]:
            raise RuntimeError("new boot does not match pinned V50")
        step("haptic_after", "set -eu; "
             "grep '^haptic ' /proc/modules; grep '^haptic_feedback ' /proc/modules; "
             'test "$(readlink /sys/bus/i2c/devices/12-005a/driver)" = '
             "../../../../../bus/i2c/drivers/haptic_hv; "
             'test "$(cat /sys/class/leds/vibrator/oplus_activate)" = 0; '
             "test -f /lib/firmware/aw8697_haptic_170.bin; "
             "dmesg | grep -q 'ram firmware update complete!'; "
             "dmesg | grep -E 'ram firmware update complete|detected aw86907' | tail -8")
        step("display_after", "set -eu; "
             "cat /var/lib/lynx-display/selection; "
             "test -c /dev/dri/card0; test -c /dev/input/event0; "
             "cat /run/lynx/display-auto.pid")
        # Direct NRP/1 listener and phone-owned media catalog.
        import socket
        with socket.create_connection((IP, 4243), timeout=5) as conn:
            conn.settimeout(5)
            conn.sendall(b"NRP/1 19 PING\nNRP/1 20 CALL HAPTIC_STATUS\n")
            received = b""
            while received.count(b"\n") < 2 and len(received) < 4096:
                received += conn.recv(4096)
        (out / "nrp_after.stdout").write_bytes(received)
        if (b"NRP/1 19 OK PONG\n" not in received or
            b"NRP/1 20 OK value=0 detail=active=0\n" not in received):
            raise RuntimeError("NRP/1 or haptic status did not recover")
        with socket.create_connection((IP, 4243), timeout=5) as conn:
            conn.settimeout(5)
            conn.sendall(b"NRP/1 21 CALL HAPTIC_SET 80 1\n")
            pulse_reply = b""
            while b"\n" not in pulse_reply and len(pulse_reply) < 4096:
                pulse_reply += conn.recv(4096)
        (out / "haptic_pulse_after.stdout").write_bytes(pulse_reply)
        if b"NRP/1 21 OK value=1 detail=duration_ms=80\n" not in pulse_reply:
            raise RuntimeError("bounded haptic pulse failed on new boot")
        time.sleep(0.25)
        step("haptic_stop_after", "set -eu; "
             'test "$(cat /sys/class/leds/vibrator/oplus_activate)" = 0; '
             "dmesg | grep 'vibrator_work_routine enter' | tail -2")
        step("media_after", "/usr/local/bin/lynx-media catalog")
        report["state"] = "new-boot-services-verified"
    except Exception as exc:
        report.update(state="failed-or-incomplete", error=str(exc))
    report["finished_ns"] = time.time_ns()
    save()
    print(json.dumps({"state": report["state"], "receipt": str(out / "result.json"),
                      "old_boot_id": report.get("old_boot_id"),
                      "new_boot_id": report.get("new_boot_id"),
                      "error": report.get("error")}), flush=True)
    if report["state"] != "new-boot-services-verified":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
