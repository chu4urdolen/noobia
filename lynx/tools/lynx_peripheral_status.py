#!/usr/bin/env python3
"""Read-only Lynx NFC, fingerprint, and headset interface status."""

import argparse
import fcntl
import json
import os
from pathlib import Path

COMPONENTS = ("nfc", "fingerprint", "headset")
HEADSET_NAME = "mt6983-mt6338 Headset Jack"
EVIOCGSW_8 = 0x8008451B
SWITCHES = {"headphone": 2, "microphone": 4, "lineout": 6, "physical": 7}


def read_switches(path):
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    try:
        bits = bytearray(8)
        fcntl.ioctl(fd, EVIOCGSW_8, bits, True)
        return int.from_bytes(bits, "little")
    finally:
        os.close(fd)


def inventory(root=Path("/"), switch_reader=read_switches):
    root = Path(root)

    def at(name):
        return root / name.lstrip("/")

    nfc_platform = at("/sys/bus/platform/devices/odm:nfc_chipset")
    nfc_driver = nfc_platform / "driver"
    nfc_nodes = [name for name in ("/dev/nq-nci", "/dev/pn544", "/dev/nfc")
                 if at(name).exists()]
    fingerprint_nodes = [name for name in ("/dev/fpsensor", "/dev/goodix_fp",
                                                 "/dev/egis_fp", "/dev/fingerprint")
                         if at(name).exists()]
    event = None
    for candidate in sorted(at("/sys/class/input").glob("event*")):
        try:
            name = (candidate / "device/name").read_text().strip()
        except OSError:
            continue
        if name == HEADSET_NAME:
            event = candidate.name
            break
    headset_bits = None
    headset_error = None
    if event is not None:
        try:
            headset_bits = switch_reader(at("/dev/input") / event)
        except OSError as exc:
            headset_error = type(exc).__name__
    return {
        "nfc": {"interface_ready": nfc_driver.exists() and bool(nfc_nodes),
                "validated": False,
                "evidence": {"platform_node": nfc_platform.exists(),
                             "driver_bound": nfc_driver.exists(), "device_nodes": nfc_nodes},
                "next": "stock oplus_nfc and nfc_i2c modules need a guarded driver trial"},
        "fingerprint": {"interface_ready": bool(fingerprint_nodes),
                        "validated": False,
                        "evidence": {"device_nodes": fingerprint_nodes},
                        "next": "identify exact sensor and secure userspace route before activation"},
        "headset": {"interface_ready": headset_bits is not None,
                    "validated": False,
                    "evidence": {"input_event": event,
                                 "switch_read_error": headset_error,
                                 "switches": ({key: bool(headset_bits & (1 << bit))
                                               for key, bit in SWITCHES.items()}
                                              if headset_bits is not None else None)},
                    "next": "physical insertion and removal trial needed to validate detection"},
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("component", choices=COMPONENTS + ("all",))
    args = parser.parse_args(argv)
    state = inventory()
    print(json.dumps(state if args.component == "all" else state[args.component],
                     sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
