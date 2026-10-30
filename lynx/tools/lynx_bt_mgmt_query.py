#!/usr/bin/env python3
"""Read only the kernel Bluetooth management controller index list."""

import ctypes
import json
from pathlib import Path
import socket
import struct

HCI_CHANNEL_CONTROL = 3
MGMT_INDEX_NONE = 0xFFFF
MGMT_OP_READ_INDEX_LIST = 3
MGMT_EV_CMD_COMPLETE = 1


def read_indexes():
    sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_RAW, socket.BTPROTO_HCI)
    try:
        address = ctypes.create_string_buffer(struct.pack("=HHH", socket.AF_BLUETOOTH,
                                                           MGMT_INDEX_NONE, HCI_CHANNEL_CONTROL))
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.bind(sock.fileno(), address, 6):
            raise OSError(ctypes.get_errno(), "Bluetooth management bind failed")
        sock.settimeout(3)
        sock.send(struct.pack("<HHH", MGMT_OP_READ_INDEX_LIST, MGMT_INDEX_NONE, 0))
        while True:
            data = sock.recv(512)
            if len(data) < 9:
                continue
            event, index, length = struct.unpack_from("<HHH", data)
            if event != MGMT_EV_CMD_COMPLETE or index != MGMT_INDEX_NONE or \
                    length + 6 > len(data):
                continue
            opcode, status = struct.unpack_from("<HB", data, 6)
            if opcode != MGMT_OP_READ_INDEX_LIST:
                continue
            if status:
                raise RuntimeError(f"Bluetooth management status {status}")
            if len(data) < 11:
                raise RuntimeError("short management index reply")
            count = struct.unpack_from("<H", data, 9)[0]
            if len(data) < 11 + count * 2:
                raise RuntimeError("truncated management index reply")
            return list(struct.unpack_from("<" + "H" * count, data, 11))
    finally:
        sock.close()


def main():
    indexes = read_indexes()
    print(json.dumps({"management_indexes": indexes,
                      "sysfs_hci0": Path("/sys/class/bluetooth/hci0").exists()}))


if __name__ == "__main__":
    main()
