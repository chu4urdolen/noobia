#!/usr/bin/env python3
"""Bounded H4 command probe for Lynx's stock /dev/stpbt transport.

Requires a working shared-radio calibration path. Run under a separate
hardware reboot watchdog. Does not pair with any device.
"""

import argparse
import json
import os
import select
import struct
import time

DEVICE = "/dev/stpbt"


def advertising_parameters():
    """LE Set Advertising Parameters: 15 bytes, per the HCI command layout."""
    return struct.pack("<HHBBB6sBB", 0x00a0, 0x00a0, 0, 0, 0, b"\0" * 6, 7, 0)


def event_frames(buffer):
    """Extract H4 events; consume complete ACL frames without misparsing them."""
    frames = []
    while buffer:
        if buffer[0] == 0x02:
            if len(buffer) < 5:
                break
            size = 5 + struct.unpack_from("<H", buffer, 3)[0]
            if len(buffer) < size:
                break
            del buffer[:size]
            continue
        if buffer[0] != 0x04:
            del buffer[0]
            continue
        if len(buffer) < 3:
            break
        size = 3 + buffer[2]
        if len(buffer) < size:
            break
        frames.append(bytes(buffer[:size]))
        del buffer[:size]
    return frames


class HCI:
    def __init__(self, fd):
        self.fd = fd
        self.buffer = bytearray()
        self.pending = []

    def command(self, opcode, params=b"", timeout=5):
        if len(params) > 255:
            raise ValueError("HCI command too large")
        packet = bytes((1, opcode & 255, opcode >> 8, len(params))) + params
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([], [self.fd], [], remaining)[1]:
                raise TimeoutError(f"HCI write timeout: {opcode:04x}")
            try:
                sent = os.write(self.fd, packet)
            except BlockingIOError:
                continue
            if sent != len(packet):
                raise OSError(f"HCI packet write incomplete: {sent}/{len(packet)}")
            break
        while time.monotonic() < deadline:
            while self.pending:
                frame = self.pending.pop(0)
                if frame[1] == 0x0e and len(frame) >= 7:
                    found = frame[4] | frame[5] << 8
                    if found == opcode:
                        status = frame[6]
                        if status:
                            raise RuntimeError(f"HCI {opcode:04x} status {status}")
                        return frame[7:]
                if frame[1] == 0x0f and len(frame) >= 7:
                    found = frame[5] | frame[6] << 8
                    if found == opcode and frame[3] != 0:
                        raise RuntimeError(f"HCI {opcode:04x} status {frame[3]}")
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([self.fd], [], [], remaining)[0]:
                break
            try:
                data = os.read(self.fd, 4096)
            except BlockingIOError:
                continue
            if not data:
                raise OSError("HCI transport closed")
            self.buffer.extend(data)
            self.pending.extend(event_frames(self.buffer))
        raise TimeoutError(f"HCI response timeout: {opcode:04x}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--advertise-seconds", type=int, default=0)
    parser.add_argument("--connect-observation", action="store_true",
                        help="record LE connection and disconnection events during advertising")
    parser.add_argument("--factory-address-hex", default="",
                        help="six factory bytes from read-only nvdata, applied to controller RAM")
    args = parser.parse_args()
    if not 0 <= args.advertise_seconds <= 30:
        parser.error("advertising duration must be 0..30 seconds")
    report = {"device": DEVICE, "advertise_seconds": args.advertise_seconds,
              "paired": False, "commands": []}
    fd = None
    advertising = False
    try:
        started = time.monotonic()
        fd = os.open(DEVICE, os.O_RDWR | os.O_NONBLOCK | os.O_CLOEXEC)
        report["open_seconds"] = round(time.monotonic() - started, 3)
        hci = HCI(fd)
        commands = [(0x0c03, "reset", b"")]
        if args.factory_address_hex:
            factory = bytes.fromhex(args.factory_address_hex)
            if len(factory) != 6 or factory == b"\0" * 6:
                raise ValueError("factory address must be six nonzero bytes")
            commands.append((0xfc1a, "set_factory_bd_address", factory[::-1]))
        commands.append((0x1009, "read_bd_address", b""))
        for opcode, name, params in commands:
            payload = hci.command(opcode, params)
            report["commands"].append({"name": name, "opcode": f"{opcode:04x}",
                                       "reply_hex": payload.hex()})
            if name == "read_bd_address" and args.factory_address_hex and payload != factory[::-1]:
                raise RuntimeError("controller address did not match factory bytes")
        if args.advertise_seconds:
            hci.command(0x2006, advertising_parameters())
            report["commands"].append({"name": "le_adv_parameters", "opcode": "2006"})
            fields = b"\x02\x01\x06\x05\x09Lynx"
            hci.command(0x2008, bytes((len(fields),)) + fields.ljust(31, b"\0"))
            report["commands"].append({"name": "le_adv_data", "opcode": "2008"})
            hci.command(0x200a, b"\x01")
            advertising = True
            report["advertising_started"] = True
            if args.connect_observation:
                deadline = time.monotonic() + args.advertise_seconds
                report["le_connection_events"] = []
                while time.monotonic() < deadline:
                    ready = select.select([fd], [], [], min(0.5, deadline - time.monotonic()))[0]
                    if not ready:
                        continue
                    try:
                        hci.buffer.extend(os.read(fd, 4096))
                    except BlockingIOError:
                        continue
                    for frame in event_frames(hci.buffer):
                        if frame[1] == 0x3e and len(frame) >= 7 and frame[3] == 0x01:
                            report["le_connection_events"].append({"kind": "le_connection_complete",
                                "status": frame[4], "handle": struct.unpack_from("<H", frame, 5)[0]})
                        elif frame[1] == 0x05 and len(frame) >= 7:
                            report["le_connection_events"].append({"kind": "disconnection_complete",
                                "status": frame[3], "handle": struct.unpack_from("<H", frame, 4)[0],
                                "reason": frame[6]})
            else:
                time.sleep(args.advertise_seconds)
        report["state"] = "hci-commands-complete"
    except Exception as exc:
        report.update(state="failed", error=str(exc))
    finally:
        if fd is not None:
            if advertising:
                try:
                    HCI(fd).command(0x200a, b"\x00", timeout=4)
                    report["advertising_stopped"] = True
                except Exception as exc:
                    report["advertising_stopped"] = False
                    report["stop_error"] = str(exc)
            os.close(fd)
    print(json.dumps(report, sort_keys=True))
    if report["state"] != "hci-commands-complete" or report.get("advertising_stopped") is False:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
