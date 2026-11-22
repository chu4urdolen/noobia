#!/usr/bin/env python3
"""Bounded local agent calls for Lynx's existing haptic NRP runtime."""

import argparse
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time

SOCKET = "/run/lynx/noobd.sock"
REPLY = re.compile(r"NRP/1 7 OK value=(-?\d+)(?: detail=([^\r\n]*))?\Z")
COMMANDS = {"status": "CALL HAPTIC_STATUS", "stop": "CALL HAPTIC_STOP",
            "pulse": "CALL HAPTIC_SET 80 1"}


def nrp(command):
    with socket.socket(socket.AF_UNIX) as conn:
        conn.settimeout(2)
        conn.connect(SOCKET)
        conn.sendall(("NRP/1 7 " + command + "\n").encode("ascii"))
        with conn.makefile("rb") as stream:
            for _ in range(4):
                data = stream.readline(4097)
                if not data.startswith(b"NRP/1 0 EVENT "):
                    break
    if len(data) > 4096 or not data.endswith(b"\n"):
        raise RuntimeError("incomplete NRP reply")
    match = REPLY.fullmatch(data.decode("ascii").rstrip("\n"))
    if match is None:
        raise RuntimeError("haptic NRP call failed")
    return int(match.group(1))


def health():
    if os.path.exists("/etc/lynx/power-thermal-guard.disable"):
        return {"boot_id": "disabled"}
    result = subprocess.run(["/usr/local/bin/lynx-status", "--assert-ready"],
                            capture_output=True, text=True, timeout=5, check=True)
    value = json.loads(result.stdout)
    battery = value["battery"]
    floor = 25 if battery["current_mA_signed"] > 0 else 50
    if (value.get("issues") or battery["capacity_percent"] < floor or
            battery["temperature_mC"] >= 35000 or value["thermal"]["max_mC"] >= 45000):
        raise RuntimeError("power or thermal guard failed")
    return value


def pulse(call=nrp, check=health, sleep=time.sleep):
    before = check()
    if call(COMMANDS["status"]) != 0:
        raise RuntimeError("haptic already active")
    try:
        if call(COMMANDS["pulse"]) != 1:
            raise RuntimeError("haptic did not start")
        sleep(0.12)
    finally:
        call(COMMANDS["stop"])
    if call(COMMANDS["status"]) != 0:
        raise RuntimeError("haptic did not stop")
    after = check()
    if after["boot_id"] != before["boot_id"]:
        raise RuntimeError("boot changed during haptic pulse")
    return {"ok": True, "duration_ms": 80, "off_verified": True,
            "boot_id": after["boot_id"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=COMMANDS)
    action = parser.parse_args(argv).action
    try:
        raw = sys.stdin.read(257)
        if len(raw) > 256 or json.loads(raw or "{}") != {}:
            raise ValueError("no arguments accepted")
        if action == "pulse":
            output = pulse()
        elif action == "stop":
            nrp(COMMANDS["stop"])
            output = {"ok": True, "off_verified": nrp(COMMANDS["status"]) == 0}
            if not output["off_verified"]:
                raise RuntimeError("haptic did not stop")
        else:
            output = {"ok": True, "active": nrp(COMMANDS["status"]) != 0}
        print(json.dumps(output, separators=(",", ":")))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired,
            subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__,
                          "detail": str(exc)[:160]}, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
