#!/usr/bin/env python3
"""Experimental V50 Wi-Fi off/on probe; first live trial lost Wi-Fi.

This is a prerequisite for RAM-only BT calibration. --check is read-only.
--run disconnects SSH temporarily and may trigger one V50 recovery reboot.
Repeat only after reviewing the first trial and its missing step-log boundary.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import time


V50_SHA = "6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59"
MODULES = {
    "btif_drv.ko": "f81ec909db5e986b2a8e23fa1c34f3f3a027a07e2da5335fc3917b8bf9615d51",
    "bt_drv_6983.ko": "f6c99218edc8e903b2ccbaac7f9e7176cd11b6129350ff738fb64d1b9ade5296",
}
STAGE = Path("/run/lynx-bt-ram")
STATE = STAGE / "wifi-cycle"
PERSIST = Path("/var/log/lynx/wifi-cycle-trial.jsonl")
WMT = Path("/dev/wmtWifi")
ADDRESS = "192.168.100.107/24"
GATEWAY = "192.168.100.1"
NEXUS = "192.168.100.106"


def command(argv, timeout=12, check=True):
    result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError(f"{argv[0]} exited {result.returncode}: {result.stderr[-180:]}")
    return result


def record(name, **fields):
    STATE.mkdir(mode=0o700, exist_ok=True)
    entry = {"event": name, "at_unix": int(time.time()), **fields}
    PERSIST.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    for path in (STATE / "events.jsonl", PERSIST):
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW,
                     0o600)
        with os.fdopen(fd, "w") as out:
            out.write(json.dumps(entry, sort_keys=True) + "\n")
            out.flush()
            os.fsync(out.fileno())


def boot_id():
    return Path("/proc/sys/kernel/random/boot_id").read_text().strip()


def preflight():
    if os.geteuid() != 0:
        raise RuntimeError("root required")
    if command(["sha256sum", "/dev/sdc39"], timeout=25).stdout.split()[0] != V50_SHA:
        raise RuntimeError("exact V50 boot image required")
    status = json.loads(command(["/usr/local/bin/lynx-status", "--assert-ready"],
                                timeout=12).stdout)
    if status["issues"] or status["battery"]["capacity_percent"] < 40 or \
            status["thermal"]["max_mC"] >= 50000:
        raise RuntimeError("V50 health, battery, or temperature gate failed")
    if not stat.S_ISCHR(WMT.stat().st_mode):
        raise RuntimeError("stock Wi-Fi control device absent")
    for name, expected in MODULES.items():
        with (STAGE / name).open("rb") as source:
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        if digest != expected:
            raise RuntimeError("BT RAM module hash differs: " + name)
    if Path("/sys/module/btif_drv").exists() or Path("/sys/module/bt_drv_6983").exists():
        raise RuntimeError("Bluetooth already registered")
    if not Path("/sys/class/net/wlan0").exists():
        raise RuntimeError("wlan0 absent")
    return status


def wpa_pids():
    found = []
    for path in Path("/proc").glob("[0-9]*/comm"):
        try:
            if path.read_text().strip() != "wpa_supplicant":
                continue
            parts = (path.parent / "cmdline").read_bytes().split(b"\0")
            if b"-i" in parts and b"wlan0" in parts:
                found.append(int(path.parent.name))
        except OSError:
            continue
    return found


def write_wmt(value):
    fd = os.open(WMT, os.O_WRONLY | os.O_NOCTTY)
    try:
        if os.write(fd, value) != len(value):
            raise RuntimeError("short stock Wi-Fi control write")
    finally:
        os.close(fd)


def restore_wifi():
    write_wmt(b"S")  # Stock source powers on Wi-Fi before station mode.
    record("station-power-on-requested")
    deadline = time.monotonic() + 20
    while not Path("/sys/class/net/wlan0").exists():
        if time.monotonic() >= deadline:
            raise RuntimeError("wlan0 did not return")
        time.sleep(0.5)
    command(["/sbin/ip", "link", "set", "wlan0", "up"], timeout=10)
    if ADDRESS not in command(["/sbin/ip", "-4", "addr", "show", "dev", "wlan0"]).stdout:
        command(["/sbin/ip", "addr", "add", ADDRESS, "dev", "wlan0"])
    command(["/sbin/ip", "route", "replace", "default", "via", GATEWAY,
             "dev", "wlan0"])
    command(["/sbin/wpa_supplicant", "-B", "-D", "nl80211", "-i", "wlan0",
             "-c", "/etc/lynx/wpa_supplicant.conf", "-f", str(STATE / "wpa.log")],
            timeout=15)
    deadline = time.monotonic() + 70
    while time.monotonic() < deadline:
        carrier = Path("/sys/class/net/wlan0/carrier")
        if carrier.exists() and carrier.read_text().strip() == "1":
            if command(["/bin/ping", "-c", "1", "-W", "2", "-I", "wlan0", NEXUS],
                       timeout=5, check=False).returncode == 0:
                return
        time.sleep(2)
    raise RuntimeError("Wi-Fi did not reconnect to Nexus")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--experimental-repeat", action="store_true")
    args = parser.parse_args()
    if args.check == args.run:
        parser.error("select exactly one of --check or --run")
    if args.run and not args.experimental_repeat:
        parser.error("first Wi-Fi cycle lost SSH; explicit --experimental-repeat required")
    status = preflight()
    if args.check:
        print(json.dumps({"state": "eligible-no-radio-change", "boot_id": boot_id(),
                          "battery_percent": status["battery"]["capacity_percent"],
                          "bt_modules_staged": True}))
        return
    if STATE.exists():
        raise RuntimeError("prior Wi-Fi cycle state exists")
    record("preflight", boot_id=boot_id(), battery_percent=status["battery"]["capacity_percent"])
    watchdog = (f"sleep 300; test -e {STATE}/cancel && exit 0; "
                f"echo timeout > {STATE}/watchdog-state; "
                f"printf '%s\\n' '{{\"event\":\"watchdog-reboot-requested\"}}' >> {PERSIST}; "
                "sync; exec /sbin/openrc-shutdown -r now")
    with (STATE / "watchdog.log").open("wb") as out:
        process = subprocess.Popen(["/bin/sh", "-c", watchdog], stdin=subprocess.DEVNULL,
                                   stdout=out, stderr=subprocess.STDOUT,
                                   start_new_session=True)
    (STATE / "watchdog.pid").write_text(str(process.pid) + "\n")
    record("watchdog-armed", pid=process.pid, seconds=300)
    try:
        for pid in wpa_pids():
            os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + 10
        while wpa_pids() and time.monotonic() < deadline:
            time.sleep(0.5)
        if wpa_pids():
            raise RuntimeError("old WPA process did not stop")
        record("wpa-stopped")
        write_wmt(b"0")
        record("wifi-power-off-requested")
        time.sleep(3)
        restore_wifi()
        if boot_id() != status["boot_id"]:
            raise RuntimeError("boot changed during probe")
        healthy = json.loads(command(["/usr/local/bin/lynx-status", "--assert-ready"],
                                     timeout=12).stdout)
        if healthy["issues"]:
            raise RuntimeError("Alpine health failed after Wi-Fi cycle")
        record("wifi-restored", battery_percent=healthy["battery"]["capacity_percent"])
        (STATE / "cancel").write_text("confirmed\n")
        record("watchdog-cancelled")
    except Exception as exc:
        record("failed", error=str(exc))
        raise


if __name__ == "__main__":
    main()
