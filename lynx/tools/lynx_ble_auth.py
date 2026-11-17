#!/usr/bin/env python3
"""Shared Nexus-issued NRP/1 request authentication for Wi-Fi and BLE."""

import hashlib
import hmac
import os
import re
import stat
import struct
from pathlib import Path
import time


DOMAIN = b"LYNX-NRP-AUTH/1\0"
FRAME = re.compile(rb"AUTH/1 ([1-9][0-9]{0,9}) ([0-9a-f]{64}) "
                   rb"(NRP/1 [0-9]{1,10} [A-Z_]+(?: [^\n]*)?)\n")
MAX_FRAME = 512
MAX_ATT_CHUNK = 20


def load_key(path):
    target = Path(path)
    metadata = target.lstat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid() or \
            metadata.st_mode & 0o077:
        raise ValueError("Nexus NRP key owner or permissions are invalid")
    key = target.read_bytes()
    if len(key) != 32:
        raise ValueError("Nexus NRP key must be 32 bytes")
    return key


def mac(key, challenge, sequence, request):
    if len(key) != 32 or len(challenge) != 32 or not 0 < sequence < 2**32:
        raise ValueError("invalid BLE authentication material")
    if not request.endswith(b"\n") or b"\n" in request[:-1]:
        raise ValueError("NRP request must be one line")
    return hmac.new(key, DOMAIN + challenge + struct.pack(">I", sequence) + request,
                    hashlib.sha256).hexdigest().encode("ascii")


def envelope(key, challenge, sequence, request, max_frame=MAX_FRAME):
    signed = mac(key, challenge, sequence, request)
    frame = b"AUTH/1 " + str(sequence).encode() + b" " + signed + b" " + request
    if len(frame) > max_frame or not FRAME.fullmatch(frame):
        raise ValueError("NRP request exceeds authenticated BLE frame limit")
    return frame


class Authenticator:
    def __init__(self, key, challenge=None, max_frame=MAX_FRAME):
        if len(key) != 32:
            raise ValueError("BLE key must be 32 bytes")
        self._key = bytes(key)
        self.challenge = bytes(challenge) if challenge is not None else os.urandom(32)
        if len(self.challenge) != 32:
            raise ValueError("BLE challenge must be 32 bytes")
        self.highest_sequence = 0
        self.max_frame = max_frame

    def challenge_line(self):
        return b"AUTH/1 CHALLENGE " + self.challenge.hex().encode("ascii") + b"\n"

    def accept(self, frame):
        if len(frame) > self.max_frame:
            raise ValueError("BLE frame too long")
        match = FRAME.fullmatch(frame)
        if not match:
            raise ValueError("malformed authenticated BLE frame")
        sequence = int(match.group(1))
        if sequence <= self.highest_sequence:
            raise ValueError("replayed BLE sequence")
        request = match.group(3) + b"\n"
        expected = mac(self._key, self.challenge, sequence, request)
        if not hmac.compare_digest(match.group(2), expected):
            raise ValueError("BLE authentication failed")
        self.highest_sequence = sequence
        return request


def fragments(frame):
    """Split one authenticated frame into writes safe at the default ATT MTU."""
    if not 1 <= len(frame) <= MAX_FRAME:
        raise ValueError("invalid BLE frame length")
    first = b"\xa0" + struct.pack(">H", len(frame)) + frame[:MAX_ATT_CHUNK - 3]
    yield first
    for start in range(MAX_ATT_CHUNK - 3, len(frame), MAX_ATT_CHUNK - 1):
        yield b"\xa1" + frame[start:start + MAX_ATT_CHUNK - 1]


class FragmentAssembler:
    def __init__(self):
        self.pending = {}

    def add(self, device, chunk):
        now = time.monotonic()
        self.pending = {peer: item for peer, item in self.pending.items() if item[2] > now}
        if not device or not 2 <= len(chunk) <= MAX_ATT_CHUNK:
            raise ValueError("invalid BLE fragment")
        if chunk[0] == 0xA0:
            if len(chunk) < 4:
                raise ValueError("short BLE start fragment")
            total = struct.unpack_from(">H", chunk, 1)[0]
            if not 1 <= total <= MAX_FRAME or len(chunk) - 3 > total:
                raise ValueError("invalid BLE total length")
            if len(self.pending) >= 16 and device not in self.pending:
                raise ValueError("too many incomplete BLE requests")
            data = bytearray(chunk[3:])
            self.pending[device] = (data, total, now + 5)
        elif chunk[0] == 0xA1:
            if device not in self.pending:
                raise ValueError("orphan BLE continuation")
            data, total, expiry = self.pending[device]
            data.extend(chunk[1:])
            if len(data) > total:
                self.pending.pop(device, None)
                raise ValueError("BLE fragment overflow")
        else:
            self.pending.pop(device, None)
            raise ValueError("unknown BLE fragment")
        data, total, expiry = self.pending[device]
        if len(data) == total:
            self.pending.pop(device, None)
            return bytes(data)
        return None
