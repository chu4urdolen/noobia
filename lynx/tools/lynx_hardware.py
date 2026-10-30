#!/usr/bin/env python3
"""Local, read-only hardware inventory shared by Lynx's tools and NRP/1."""

import argparse
import json
from pathlib import Path
import sys

DEVICES = ("microphone", "flashlight", "gnss", "bluetooth", "camera")


def inventory(root=Path("/")):
    """Report observed interfaces; an interface is never a claim of operation."""
    def at(path):
        return root / path.lstrip("/")

    def exists(path):
        return at(path).exists()

    def names(path, pattern):
        return sorted(p.name for p in at(path).glob(pattern))

    def module(name):
        return exists("/sys/module/" + name)

    cards = at("/proc/asound/cards")
    try:
        has_card = "mt6983mt6338" in cards.read_text()
    except OSError:
        has_card = False
    capture = exists("/dev/snd/pcmC0D11c")
    flash_chip = exists("/sys/bus/i2c/devices/6-0063")
    flash_bound = exists("/sys/bus/i2c/devices/6-0063/driver")
    # ccci_c2k_agps is a modem assistance node, not a usable GNSS receiver.
    gps_nodes = ([name for name in ("stpgps", "gps", "gps0")
                  if exists("/dev/" + name)] +
                 names("/dev", "gnss*") + names("/dev", "gps_nd*") +
                 names("/dev", "gps_da*") + names("/dev", "gps_mb*") +
                 names("/dev", "gpsdl*"))
    gps_power = exists("/dev/gps_pwr")
    gps_scp = exists("/dev/gps2scp")
    hci = names("/sys/class/bluetooth", "hci*")
    stpbt = exists("/dev/stpbt")
    video = names("/dev", "video*")
    media = names("/dev", "media*")
    observations = {
        "microphone": {
            "interface_ready": has_card and capture,
            "validated": has_card and capture,
            "evidence": {"alsa_card": has_card, "capture_pcm": capture},
            "next": "external clap validated V50 capture; keep the ALSA route guarded",
        },
        "flashlight": {
            "interface_ready": flash_bound and exists("/dev/flashlight"),
            "validated": False,
            "evidence": {"chip_present": flash_chip, "driver_bound": flash_bound,
                         "device_node": exists("/dev/flashlight")},
            "next": "resolve flashlight core unload hang before another driver trial",
        },
        "gnss": {
            "interface_ready": bool(gps_nodes) and module("gps_drv_dl_v050"),
            "validated": False,
            "evidence": {"nodes": gps_nodes, "power_node": gps_power,
                         "scp_node": gps_scp,
                         "driver_loaded": module("gps_drv_dl_v050"),
                         "nmea_trial_verified": True, "position_fix_verified": False},
            "next": "run a guarded outdoor position trial when Lynx has sky view",
        },
        "bluetooth": {
            "interface_ready": stpbt and module("bt_drv_6983"),
            "validated": False,
            "evidence": {"hci": hci, "stpbt": stpbt,
                         "driver_loaded": module("bt_drv_6983"),
                         "hci_exchange_trial_verified": True,
                         "nexus_le_connection_trial_verified": True,
                         "noobian_bluetooth_transport_verified": False},
            "next": "bridge vendor HCI to a bounded BlueZ or direct ATT transport",
        },
        "camera": {
            "interface_ready": bool(video and media),
            "validated": False,
            "evidence": {"video_nodes": video, "media_nodes": media,
                         "driver_loaded": module("imgsensor")},
            "next": "map active sensor and CCU dependencies before streaming",
        },
    }
    return observations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("status", "tool"))
    parser.add_argument("device", choices=DEVICES + ("all", "microphone_level"))
    args = parser.parse_args()
    if args.command == "tool":
        try:
            raw = sys.stdin.read(4097)
            if len(raw) > 4096:
                parser.error("JSON input exceeds 4096 bytes")
            request = json.loads(raw)
        except (ValueError, UnicodeError) as exc:
            parser.error(f"invalid JSON input: {exc}")
        if request != {}:
            parser.error("this tool currently accepts an empty JSON object only")
    if args.device == "microphone_level":
        if args.command != "tool":
            parser.error("microphone_level is a tool action")
        from lynx_microphone_level import sample_level
        try:
            result = sample_level()
        except Exception as exc:
            print(json.dumps({"captured": False, "error": str(exc),
                              "raw_audio_retained": False}, sort_keys=True))
            raise SystemExit(1)
    else:
        state = inventory()
        result = state if args.device == "all" else state[args.device]
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
