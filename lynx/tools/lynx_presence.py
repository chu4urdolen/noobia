#!/usr/bin/env python3
"""Low-duty Nexus presence monitor for Lynx's USB, Wi-Fi, and BLE link."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import time


USB_VENDOR = "0e8d"
USB_PRODUCT = "201c"
WIFI_ADDRESS = "192.168.100.107"
SSH_PORT = 2222
BT_ADDRESS = "AC:C0:48:6D:F1:FA"
DEFAULT_STATE = Path("/noobia/lynx/state/presence")


def now():
    return datetime.now(timezone.utc).isoformat()


def usb_probe(sysfs=Path("/sys/bus/usb/devices")):
    """Identify known Lynx USB and the standard Fastboot interface passively."""
    present = fastboot = False
    try:
        devices = list(sysfs.iterdir())
    except OSError:
        return {"usb_present": False, "fastboot_usb": False}
    for device in devices:
        try:
            vendor = (device / "idVendor").read_text().strip().lower()
            product = (device / "idProduct").read_text().strip().lower()
        except OSError:
            continue
        if (vendor, product) != (USB_VENDOR, USB_PRODUCT):
            continue
        present = True
        for interface in sysfs.glob(device.name + ":*"):
            try:
                identifiers = tuple((interface / name).read_text().strip().lower()
                                    for name in ("bInterfaceClass", "bInterfaceSubClass",
                                                 "bInterfaceProtocol"))
            except OSError:
                continue
            if identifiers == ("ff", "42", "03"):
                fastboot = True
                break
    return {"usb_present": present, "fastboot_usb": fastboot}


def wifi_probe(timeout=0.6):
    try:
        with socket.create_connection((WIFI_ADDRESS, SSH_PORT), timeout=timeout):
            return True
    except OSError:
        return False


def bluetooth_probe():
    try:
        result = subprocess.run(["bluetoothctl", "info", BT_ADDRESS],
                                capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and bool(re.search(r"(?m)^\s*Connected:\s*yes\s*$",
                                               result.stdout))


def battery_probe():
    # A single authenticated SSH read every five minutes while Wi-Fi is up.
    from lynx_wifi_v19_contact import ssh_command
    argv = ssh_command(
        WIFI_ADDRESS,
        "/usr/local/bin/lynx-status; "
        "cat /sys/class/power_supply/11e01000.i2c:mt6375@34:chg/status 2>/dev/null || true")
    argv[-2:-2] = ["-p", str(SSH_PORT)]
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=8)
        lines = result.stdout.splitlines()
        status = json.loads(lines[0]) if result.returncode == 0 and lines else {}
        battery = status.get("battery", {})
        return {"percent": battery["capacity_percent"],
                "temperature_mC": battery["temperature_mC"],
                "current_mA_signed": battery["current_mA_signed"],
                "voltage_mV": battery["voltage_mV"],
                "charger_status": lines[1] if len(lines) > 1 else "unknown",
                "boot_id": status["boot_id"], "observed_at_utc": now()}
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError):
        return None


def location(signals):
    if signals["fastboot_usb"]:
        return "fastboot_usb"
    if signals["wifi_ssh"]:
        return "alpine_wifi"
    if signals["bluetooth_connected"]:
        return "bluetooth_connected"
    if signals["usb_present"]:
        return "usb_other_mode"
    return "not_observed"


def write_status(directory, status, prior):
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / "current.json"
    temporary = directory / "current.tmp"
    temporary.write_text(json.dumps(status, sort_keys=True, indent=2) + "\n")
    temporary.replace(destination)
    changed = prior is None or any(status.get(key) != prior.get(key) for key in
                                   ("state", "usb_present", "fastboot_usb", "wifi_ssh",
                                    "bluetooth_connected"))
    if changed:
        with (directory / "transitions.jsonl").open("a") as history:
            history.write(json.dumps(status, sort_keys=True) + "\n")
        print(json.dumps({"at": status["observed_at_utc"], "state": status["state"],
                          "usb": status["usb_present"], "wifi": status["wifi_ssh"],
                          "bluetooth": status["bluetooth_connected"]}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interval", type=int, default=30)
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if not 10 <= args.interval <= 300:
        parser.error("interval must be 10..300 seconds")
    os.umask(0o077)
    previous = None
    current = args.state_dir / "current.json"
    if current.is_file():
        try:
            previous = json.loads(current.read_text())
        except (OSError, ValueError):
            pass
    last_bt = 0.0
    last_battery = 0.0
    bt_connected = bool(previous and previous.get("bluetooth_connected"))
    battery = previous.get("battery") if previous else None
    while True:
        started = time.monotonic()
        signals = usb_probe()
        signals["wifi_ssh"] = wifi_probe()
        if started - last_bt >= 60 or args.once:
            bt_connected = bluetooth_probe()
            last_bt = started
        signals["bluetooth_connected"] = bt_connected
        if signals["wifi_ssh"] and (started - last_battery >= 300 or args.once):
            fresh = battery_probe()
            if fresh is not None:
                battery = fresh
            last_battery = started
        status = {"schema": 1, "observed_at_utc": now(), "state": location(signals),
                  **signals, "battery": battery,
                  "bluetooth_note": "connected link only; no active radio scan"}
        write_status(args.state_dir, status, previous)
        previous = status
        if args.once:
            print(json.dumps(status, sort_keys=True))
            return
        time.sleep(max(0, args.interval - (time.monotonic() - started)))


if __name__ == "__main__":
    main()
