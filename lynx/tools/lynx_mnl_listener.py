#!/usr/bin/env python3
"""Capture MediaTek mnld datagrams; optionally issue verified start and stop."""

import argparse
import json
from pathlib import Path
import socket
import struct
import time

HAL_SOCKET = b"\0mtk_mnl2hal".ljust(108, b"\0")
MNL_SOCKET = b"\0mtk_hal2mnl".ljust(108, b"\0")
START = struct.pack("<IIf", 1, 102, 1.4)
STOP = struct.pack("<II", 1, 103)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--start-trial", action="store_true")
    parser.add_argument("--seconds", type=int, default=9)
    parser.add_argument("--stop-after", type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 90 or not 1 <= args.stop_after < args.seconds:
        parser.error("bounded listener duration required")
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    sock.bind(HAL_SOCKET)
    sock.settimeout(0.2)
    started_at = None
    stopped = False
    deadline = time.monotonic() + args.seconds
    with args.output.open("w", buffering=1) as out:
        while time.monotonic() < deadline:
            if started_at is not None and not stopped and time.monotonic() - started_at >= args.stop_after:
                try:
                    sent = sock.sendto(STOP, MNL_SOCKET)
                    out.write(json.dumps({"event": "stop_sent", "bytes": sent}) + "\n")
                except OSError as exc:
                    out.write(json.dumps({"event": "stop_error", "errno": exc.errno}) + "\n")
                stopped = True
            try:
                data = sock.recv(8192)
            except socket.timeout:
                continue
            out.write(json.dumps({"event": "message", "monotonic": time.monotonic(),
                                  "hex": data.hex(), "length": len(data)}) + "\n")
            if (args.start_trial and started_at is None and len(data) >= 8 and
                    struct.unpack_from("<II", data) == (1, 308)):
                try:
                    sent = sock.sendto(START, MNL_SOCKET)
                    started_at = time.monotonic()
                    out.write(json.dumps({"event": "start_sent", "bytes": sent,
                                          "packet_hex": START.hex()}) + "\n")
                except OSError as exc:
                    out.write(json.dumps({"event": "start_error", "errno": exc.errno}) + "\n")


if __name__ == "__main__":
    main()
