#!/usr/bin/env python3
"""Request one short LM3642 torch pulse; never expose continuous ON."""

import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import time

TORCH = Path("/sys/devices/virtual/flashlight_core/flashlight/flashlight_torch")
DT = Path("/sys/firmware/devicetree/base/i2c@11e02000/lm3642@63/flash@0")
MODULES = ("mtk_battery_oc_throttling", "flashlight", "lm3642_22823")
LOCK = Path("/run/lynx/flashlight-pulse.lock")
LAST = Path("/run/lynx/flashlight-last-pulse")
ON = "0 0 0 1"
OFF = "0 0 0 0"


def status():
    lines = TORCH.read_text().splitlines()
    rows = [line.split() for line in lines[1:] if line.strip()]
    if rows != [["0", "0", "0", "0"]]:
        raise RuntimeError(f"unexpected flashlight state: {rows!r}")


def health():
    process = subprocess.run(["/usr/local/bin/lynx-status", "--assert-ready"],
                             capture_output=True, text=True, timeout=8, check=True)
    value = json.loads(process.stdout)
    minimum = 25 if value["battery"]["current_mA_signed"] > 0 else 50
    if (value["issues"] or value["battery"]["capacity_percent"] < minimum or
            value["battery"]["temperature_mC"] >= 35000 or
            value["thermal"]["max_mC"] >= 45000):
        raise RuntimeError("battery, thermal, or Alpine health gate failed")
    return value


def write_off():
    TORCH.write_text(OFF)


def stop():
    if not TORCH.is_file():
        return {"driver_present": False, "off_requested": False,
                "off_verified": False}
    with LOCK.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        write_off()
        status()
    return {"driver_present": True, "off_requested": True,
            "off_verified": True}


def pulse(milliseconds):
    if not 20 <= milliseconds <= 100:
        raise ValueError("duration must be 20..100 ms")
    if not TORCH.is_file() or not Path("/dev/flashlight").exists():
        raise RuntimeError("flashlight interface absent")
    if not Path("/sys/bus/i2c/devices/6-0063/driver").exists():
        raise RuntimeError("LM3642 is not bound")
    loaded = {line.split()[0] for line in Path("/proc/modules").read_text().splitlines()}
    if not set(MODULES).issubset(loaded):
        raise RuntimeError("required flashlight modules are absent")
    for name in ("type", "ct", "part", "reg"):
        if int.from_bytes((DT / name).read_bytes(), "big") != 0:
            raise RuntimeError("unexpected flashlight device-tree channel")
    if len(list(DT.parent.glob("flash@*"))) != 1:
        raise RuntimeError("unexpected extra flashlight channel")
    before = health()
    with LOCK.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            previous = float(LAST.read_text())
        except (OSError, ValueError):
            previous = -100.0
        now = time.monotonic()
        if now - previous < 10:
            raise RuntimeError("flashlight cooldown: 10 seconds")
        status()
        LAST.write_text(str(now))
        child = os.fork()
        if child == 0:
            try:
                time.sleep(0.5)
                write_off()
            finally:
                os._exit(0)
        on_sent = False
        try:
            TORCH.write_text(ON)
            on_sent = True
            time.sleep(milliseconds / 1000)
        finally:
            write_off()
            os.waitpid(child, 0)
        status()
    after = health()
    if before["boot_id"] != after["boot_id"]:
        raise RuntimeError("boot changed during pulse")
    return {"commanded": on_sent, "duration_ms": milliseconds,
            "off_verified": True, "visual_confirmation": False,
            "boot_id": after["boot_id"],
            "battery_percent": after["battery"]["capacity_percent"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--off", action="store_true")
    parser.add_argument("--duration-ms", type=int, default=100)
    args = parser.parse_args()
    try:
        print(json.dumps(stop() if args.off else pulse(args.duration_ms), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"commanded": False, "error": str(exc)}, sort_keys=True))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
