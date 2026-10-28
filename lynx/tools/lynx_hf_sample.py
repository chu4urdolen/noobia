#!/usr/bin/env python3
"""Bounded Lynx hf_manager accelerometer sample; run on the phone only."""

import argparse
import fcntl
import json
import os
import select
import signal
import struct
import time


DEVICE = "/dev/hf_manager"
IOCTL_PACKET_SIZE = 68
REGISTER_STATUS = (3 << 30) | (IOCTL_PACKET_SIZE << 16) | (ord("a") << 8) | 1
SENSOR_INFO = (3 << 30) | (IOCTL_PACKET_SIZE << 16) | (ord("a") << 8) | 6
EVENT = struct.Struct("<qBBBB16i")
SUPPORTED = (1, 2, 4, 8, 98)  # Motion, proximity, rear ambient light on Lynx.


def command(sensor, action, delay_ns=0):
    # hf_manager_cmd: sensor_type, action bitfield, length, pad, 48-byte data.
    return struct.pack("<BBBBqq", sensor, action, 16 if action else 0, 0,
                       delay_ns, 0) + bytes(32)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=2.0)
    parser.add_argument("--events", type=int, default=16)
    parser.add_argument("--sensor", type=int, choices=SUPPORTED, default=1)
    args = parser.parse_args()
    if not 0.5 <= args.seconds <= 3.0:
        parser.error("sample duration must be 0.5..3 seconds")
    if not 1 <= args.events <= 16:
        parser.error("event count must be 1..16")

    def interrupted(_signum, _frame):
        raise InterruptedError("trial interrupted")

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    result = {"sensor_type": args.sensor, "sample_seconds": args.seconds,
              "events": [], "enabled": False, "disabled": False}
    fd = os.open(DEVICE, os.O_RDWR | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        packet = bytearray(IOCTL_PACKET_SIZE)
        packet[0] = args.sensor
        fcntl.ioctl(fd, REGISTER_STATUS, packet, True)
        if not packet[4]:
            raise RuntimeError("sensor not registered")
        packet = bytearray(IOCTL_PACKET_SIZE)
        packet[0] = args.sensor
        fcntl.ioctl(fd, SENSOR_INFO, packet, True)
        sensor_type, gain, name, vendor = struct.unpack_from("<B3xI16s16s", packet, 4)
        result["info"] = {"type": sensor_type, "gain": gain,
                          "name": name.split(b"\0", 1)[0].decode(errors="replace"),
                          "vendor": vendor.split(b"\0", 1)[0].decode(errors="replace")}
        if os.write(fd, command(args.sensor, 1, 100_000_000)) != 0:
            raise RuntimeError("unexpected enable write length")
        result["enabled"] = True
        poller = select.poll()
        poller.register(fd, select.POLLIN)
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline and len(result["events"]) < args.events:
            remaining = max(1, int((deadline - time.monotonic()) * 1000))
            if not poller.poll(min(remaining, 250)):
                continue
            data = os.read(fd, EVENT.size * 16)
            if len(data) % EVENT.size:
                raise RuntimeError("misaligned sensor event read")
            for offset in range(0, len(data), EVENT.size):
                timestamp, sensor, accuracy, action, _pad, *words = EVENT.unpack_from(data, offset)
                if sensor == args.sensor and action == 0:
                    result["events"].append({"timestamp_ns": timestamp,
                                              "accuracy": accuracy,
                                              "raw_xyz": words[:3]})
                    if len(result["events"]) >= args.events:
                        break
    finally:
        if result["enabled"]:
            try:
                result["disabled"] = os.write(fd, command(args.sensor, 0)) == 0
            finally:
                os.close(fd)
        else:
            os.close(fd)
    print(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()
