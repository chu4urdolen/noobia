#!/usr/bin/env python3
"""Bounded H4 bridge from stock /dev/stpbt to the built-in HCI UART driver.

The PTY slave becomes an N_HCI line discipline. This is a transport probe,
not a persistent Bluetooth service or a Noobian protocol endpoint.
"""

import argparse
import fcntl
import json
import os
from pathlib import Path
import select
import signal
import struct
import termios
import time
import tty

STPBT = "/dev/stpbt"
N_HCI = 15
HCI_UART_H4 = 0
HCIUARTSETPROTO = 0x400455C8
HCIUARTGETDEVICE = 0x800455CA
MAX_PENDING = 65536


def correct_sync_train_capability(data, buffer, report):
    """Hide only a feature that this controller advertises but rejects.

    The Linux HCI core uses page 2, feature byte 0, bit 2 to decide whether
    to issue Read Synchronization Train Parameters. MT6983 returns status 1
    (unknown command) to that request, aborting HCI setup. No other frame or
    feature bit is changed.
    """
    buffer.extend(data)
    output = bytearray()
    while buffer:
        kind = buffer[0]
        if kind == 4:
            if len(buffer) < 3:
                break
            size = 3 + buffer[2]
        elif kind == 2:
            if len(buffer) < 5:
                break
            size = 5 + struct.unpack_from("<H", buffer, 3)[0]
        else:
            output.append(buffer.pop(0))
            continue
        if len(buffer) < size:
            break
        frame = bytearray(buffer[:size])
        del buffer[:size]
        if (kind == 4 and len(frame) >= 17 and frame[1] == 0x0E and
                struct.unpack_from("<H", frame, 4)[0] == 0x1004 and
                frame[6] == 0 and frame[7] == 2 and frame[9] & 0x04):
            report["sync_train_capability_corrected"] += 1
            frame[9] &= ~0x04
        output.extend(frame)
    if len(buffer) > MAX_PENDING:
        raise RuntimeError("H4 frame buffer exceeded limit")
    return output


def record_h4(data, buffer, direction, report):
    """Record command opcodes and event statuses, never payload or addresses."""
    buffer.extend(data)
    key = "host_commands" if direction == "host" else "controller_events"
    while buffer:
        packet_type = buffer[0]
        if packet_type == 1 and direction == "host":
            if len(buffer) < 4:
                break
            size = 4 + buffer[3]
        elif packet_type == 4 and direction == "controller":
            if len(buffer) < 3:
                break
            size = 3 + buffer[2]
        elif packet_type == 2:
            if len(buffer) < 5:
                break
            size = 5 + struct.unpack_from("<H", buffer, 3)[0]
        else:
            del buffer[0]
            continue
        if len(buffer) < size:
            break
        frame = bytes(buffer[:size])
        del buffer[:size]
        if len(report[key]) >= 64:
            continue
        if direction == "host" and packet_type == 1:
            report[key].append(f"{struct.unpack_from('<H', frame, 1)[0]:04x}")
        elif direction == "controller" and packet_type == 4:
            code = frame[1]
            item = {"event": f"{code:02x}"}
            if code == 0x0E and len(frame) >= 7:
                item.update(opcode=f"{struct.unpack_from('<H', frame, 4)[0]:04x}",
                            status=frame[6])
                if item["opcode"] == "1004" and len(frame) >= 17:
                    item.update(page=frame[7], max_page=frame[8],
                                first_feature_byte=frame[9])
            elif code == 0x0F and len(frame) >= 7:
                item.update(opcode=f"{struct.unpack_from('<H', frame, 5)[0]:04x}",
                            status=frame[3])
            report[key].append(item)


def copy_ready(source, pending, trace_buffer, direction, report,
               correction_buffer=None):
    """Read one chunk into a bounded pending buffer; False means EOF."""
    try:
        data = os.read(source, 4096)
    except BlockingIOError:
        return True
    if not data:
        return False
    record_h4(data, trace_buffer, direction, report)
    pending.extend(correct_sync_train_capability(data, correction_buffer, report)
                   if correction_buffer is not None else data)
    if len(pending) > MAX_PENDING:
        raise RuntimeError("H4 bridge backlog exceeded limit")
    return True


def flush_ready(destination, pending):
    try:
        sent = os.write(destination, pending)
    except BlockingIOError:
        return 0
    if sent <= 0:
        raise RuntimeError("H4 bridge write returned no progress")
    del pending[:sent]
    return sent


def run(seconds, mask_broken_sync_train=False, factory_address_hex="",
        stop_requested=lambda: False):
    report = {"state": "starting", "duration_seconds": seconds,
              "partition_writes": False, "source": STPBT,
              "capability_filter_enabled": mask_broken_sync_train,
              "sync_train_capability_corrected": 0}
    stpbt = master = slave = None
    try:
        report["phase"] = "open_vendor"
        stpbt = os.open(STPBT, os.O_RDWR | os.O_NONBLOCK | os.O_CLOEXEC)
        if factory_address_hex:
            from lynx_bluetooth_hci_probe import HCI
            factory = bytes.fromhex(factory_address_hex)
            if len(factory) != 6 or factory == b"\0" * 6 or factory[:3] == b"\x00\x00\x46":
                raise ValueError("invalid factory Bluetooth address")
            report["phase"] = "apply_factory_address_to_controller_ram"
            hci = HCI(stpbt)
            hci.command(0x0C03)
            hci.command(0xFC1A, factory[::-1])
            if hci.command(0x1009) != factory[::-1]:
                raise RuntimeError("controller did not retain factory address")
            report["factory_address_applied"] = True
        report["phase"] = "open_pty"
        master, slave = os.openpty()
        report["phase"] = "configure_pty"
        tty.setraw(slave)
        os.set_blocking(master, False)
        report["phase"] = "set_hci_line_discipline"
        fcntl.ioctl(slave, termios.TIOCSETD, struct.pack("i", N_HCI))
        report["phase"] = "register_h4_controller"
        fcntl.ioctl(slave, HCIUARTSETPROTO, HCI_UART_H4)
        device_id = fcntl.ioctl(slave, HCIUARTGETDEVICE, 0)
        if not 0 <= device_id < 256:
            raise RuntimeError("HCI UART did not register a controller")
        node = Path(f"/sys/class/bluetooth/hci{device_id}")
        report.update(hci_index=device_id, registered=node.exists())
        if not report["registered"]:
            raise RuntimeError("HCI controller missing in sysfs")
        to_pty = bytearray()
        to_stpbt = bytearray()
        host_trace = bytearray()
        controller_trace = bytearray()
        correction_buffer = bytearray() if mask_broken_sync_train else None
        report["host_commands"] = []
        report["controller_events"] = []
        report["bytes_vendor_to_hci"] = 0
        report["bytes_hci_to_vendor"] = 0
        report["phase"] = "forward_h4"
        deadline = time.monotonic() + seconds if seconds else None
        while not stop_requested() and (deadline is None or time.monotonic() < deadline):
            readers = [stpbt, master]
            writers = ([master] if to_pty else []) + ([stpbt] if to_stpbt else [])
            ready_read, ready_write, _ = select.select(readers, writers, [],
                                                       max(0.0, min(0.2, deadline - time.monotonic()))
                                                       if deadline is not None else 0.2)
            if stpbt in ready_read and not copy_ready(stpbt, to_pty,
                                                       controller_trace, "controller", report,
                                                       correction_buffer):
                raise RuntimeError("vendor transport closed")
            if master in ready_read and not copy_ready(master, to_stpbt,
                                                        host_trace, "host", report):
                raise RuntimeError("HCI UART PTY closed")
            if master in ready_write:
                report["bytes_vendor_to_hci"] += flush_ready(master, to_pty)
            if stpbt in ready_write:
                report["bytes_hci_to_vendor"] += flush_ready(stpbt, to_stpbt)
        report["registered_at_end"] = node.exists()
        report["state"] = "bridge-stopped" if seconds == 0 else "bridge-complete"
    except Exception as exc:
        report.update(state="bridge-failed", error=str(exc))
        if isinstance(exc, OSError):
            report["errno"] = exc.errno
    finally:
        for fd in (slave, master, stpbt):
            if fd is not None:
                os.close(fd)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=8)
    parser.add_argument("--mask-broken-sync-train", action="store_true")
    parser.add_argument("--factory-address-hex", default="",
                        help="verified six-byte nvdata address, applied to controller RAM")
    parser.add_argument("--factory-address-file", default="",
                        help="root-only RAM file containing six raw factory address bytes")
    args = parser.parse_args()
    if not 0 <= args.seconds <= 45:
        parser.error("bounded duration required")
    stopping = False

    def stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    if args.seconds == 0:
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
    if args.factory_address_file and args.factory_address_hex:
        parser.error("select only one factory address source")
    factory_address_hex = (Path(args.factory_address_file).read_bytes().hex()
                           if args.factory_address_file else args.factory_address_hex)
    result = run(args.seconds, args.mask_broken_sync_train, factory_address_hex,
                 stop_requested=lambda: stopping)
    print(json.dumps(result, sort_keys=True))
    if result["state"] not in ("bridge-complete", "bridge-stopped"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
