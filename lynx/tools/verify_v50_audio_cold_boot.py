#!/usr/bin/env python3
"""One guarded reboot to verify Lynx audio starts without Nexus intervention."""

import json
from pathlib import Path
import socket
import subprocess
import sys
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
IP = "192.168.100.107"
KERNEL = "5.10.149-android12-9-o-g311738fbb5a8"
INIT = "b560f233f5ecf838b5e948d0cd3685b676a84f3097adb00d2c8bfa6e5446ab1f"
BOOT = "6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59"


def ssh(command, port=2222, timeout=12):
    args = ssh_command(IP, command)
    args[-2:-2] = ["-p", str(port)]
    return subprocess.run(args, capture_output=True, timeout=timeout)


def main():
    out = ROOT / "logs" / f"v50-audio-cold-boot-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "preflight", "reboot_sent": False,
              "boot_partition_writes": False, "steps": []}

    def save():
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")

    def step(name, command, port=2222, timeout=12, allow_disconnect=False):
        result = ssh(command, port, timeout)
        (out / f"{name}.stdout").write_bytes(result.stdout)
        (out / f"{name}.stderr").write_bytes(result.stderr)
        report["steps"].append({"name": name, "exit": result.returncode})
        save()
        if result.returncode and not allow_disconnect:
            raise RuntimeError(f"{name} failed; see saved output")
        return result.stdout.decode(errors="replace")

    try:
        before = step("identity_before", "cat /proc/sys/kernel/random/boot_id; "
                      "uname -r; sha256sum /init /dev/sdc39 | cut -c1-64",
                      port=22, timeout=25).splitlines()
        if len(before) != 4 or before[1:] != [KERNEL, INIT, BOOT]:
            raise RuntimeError("preflight identity does not match V50")
        report["old_boot_id"] = before[0]
        health = json.loads(step("health_before", "/usr/local/bin/lynx-status --assert-ready"))
        battery = health["battery"]
        if (health["boot_id"] != before[0] or battery["capacity_percent"] < 40 or
            battery["current_mA_signed"] <= 0 or battery["temperature_mC"] >= 35000 or
            health["thermal"]["max_mC"] >= 45000):
            raise RuntimeError("battery or thermal guard refused reboot")
        report["battery_percent_before"] = battery["capacity_percent"]
        step("audio_before", "set -eu; rc-service lynx-audio status; "
             "test -L /etc/runlevels/default/lynx-audio; "
             "grep -q mt6983mt6338 /proc/asound/cards; "
             "test -x /usr/local/bin/lynx-audio-bootstrap; "
             "test -r /var/lib/lynx-audio/v1/modules.sha256")
        step("reboot", "/sbin/openrc-shutdown -r now", timeout=12, allow_disconnect=True)
        report.update(state="awaiting-new-boot", reboot_sent=True)
        save()
        print("reboot sent; waiting for Alpine and audio", flush=True)

        deadline = time.monotonic() + 650
        new_id = None
        attempt = 0
        while time.monotonic() < deadline:
            attempt += 1
            try:
                result = ssh("cat /proc/sys/kernel/random/boot_id", timeout=8)
            except subprocess.TimeoutExpired:
                result = None
            if result and result.returncode == 0:
                observed = result.stdout.decode(errors="replace").strip()
                if observed and observed != before[0]:
                    new_id = observed
                    break
            if attempt % 10 == 0:
                print(f"watch {attempt}: waiting for new Alpine SSH", flush=True)
            time.sleep(3)
        if not new_id:
            raise RuntimeError("new Alpine SSH did not return")
        report["new_boot_id"] = new_id
        print(f"new Alpine boot {new_id}", flush=True)

        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            try:
                result = ssh("set -eu; /usr/local/bin/lynx-status --assert-ready >/dev/null; "
                             "rc-service lynx-audio status; "
                             "grep -q mt6983mt6338 /proc/asound/cards; "
                             "amixer -c0 cget name='TFA98XX Firmware' | grep -q ': values=1'; "
                             "amixer -c0 cget name=Speaker_L_Mute_Switch | grep -q ': values=1'; "
                             "amixer -c0 cget name=Speaker_R_Mute_Switch | grep -q ': values=1'",
                             timeout=20)
            except subprocess.TimeoutExpired:
                time.sleep(3)
                continue
            if result.returncode == 0:
                (out / "audio_after.stdout").write_bytes(result.stdout)
                break
            time.sleep(3)
        else:
            raise RuntimeError("audio service or health not ready after Alpine boot")

        after = step("identity_after", "cat /proc/sys/kernel/random/boot_id; "
                     "uname -r; sha256sum /init /dev/sdc39 | cut -c1-64",
                     port=22, timeout=25).splitlines()
        if after != [new_id, KERNEL, INIT, BOOT]:
            raise RuntimeError("V50 identity changed after reboot")
        with socket.create_connection((IP, 4243), timeout=5) as conn:
            conn.settimeout(5)
            conn.sendall(b"NRP/1 61 CALL AUDIO_READY\n")
            answer = conn.recv(512)
        (out / "nrp_audio_after.stdout").write_bytes(answer)
        if b"NRP/1 61 OK value=1 detail=card=1 firmware=1\n" not in answer:
            raise RuntimeError("Noob audio readiness did not recover")
        report["state"] = "audio-automatic-cold-boot-verified"
    except Exception as exc:
        report.update(state="failed-or-incomplete", error=str(exc))
    report["finished_ns"] = time.time_ns()
    save()
    print(json.dumps({"state": report["state"], "receipt": str(out / "result.json"),
                      "error": report.get("error")}), flush=True)
    if report["state"] != "audio-automatic-cold-boot-verified":
        sys.exit(1)


if __name__ == "__main__":
    main()
