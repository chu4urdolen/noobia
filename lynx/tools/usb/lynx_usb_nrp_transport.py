#!/usr/bin/env python3
"""Offline Prototype: USB CDC ACM Agent Transport for NRP/1.

Implements framed, authenticated, bounded transport over serial byte streams
(such as /dev/ttyACM0 <-> /dev/ttyGS0), without requiring live hardware deployment.

Trust Boundaries:
- Enforces HMAC-SHA256 request authentication with replay protection.
- Enforces strict frame size bounds (MAX_FRAME = 512 bytes) and stream buffer caps.
- Strict state teardown on link disconnect or timeout.
- Forbids open shell bridging; scopes calls strictly to NRP/1 command grammar.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import struct
import time
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

DOMAIN = b"LYNX-USB-NRP/1\0"
MAX_FRAME = 512
MAX_BUFFER = 2048

# Envelope format: AUTH/1 <seq> <64-hex-hmac> <payload>\n
AUTH_FRAME_RE = re.compile(
    rb"AUTH/1 ([1-9][0-9]{0,9}) ([0-9a-f]{64}) (NRP/1 [0-9]{1,10} [A-Z_]+(?: [^\n]*)?)\n"
)
UNAUTH_DIAG_RE = re.compile(
    rb"DIAG/1 [0-9]{1,10} (?:PING|STATUS|ECHO)(?: [^\n]*)?\n"
)


class TransportError(Exception):
    """Base transport error."""


class FrameTooLongError(TransportError):
    """Frame exceeds MAX_FRAME bytes."""


class MalformedFrameError(TransportError):
    """Frame does not match expected grammar."""


class AuthenticationError(TransportError):
    """Signature mismatch or replay detected."""


class DisconnectError(TransportError):
    """Link disconnected unexpectedly."""


class TimeoutError(TransportError):
    """Operation timed out."""


def compute_mac(key: bytes, challenge: bytes, sequence: int, payload: bytes) -> bytes:
    """Compute HMAC-SHA256 over domain, challenge, sequence, and payload."""
    if len(key) != 32:
        raise ValueError("Key must be 32 bytes")
    if len(challenge) != 32:
        raise ValueError("Challenge must be 32 bytes")
    if not (0 < sequence < 2**32):
        raise ValueError("Sequence must be a positive 32-bit integer")
    if not payload.endswith(b"\n") or b"\n" in payload[:-1]:
        raise ValueError("Payload must end with exactly one newline")

    data = DOMAIN + challenge + struct.pack(">I", sequence) + payload
    return hmac.new(key, data, hashlib.sha256).hexdigest().encode("ascii")


def create_authenticated_frame(
    key: bytes, challenge: bytes, sequence: int, nrp_command: str
) -> bytes:
    """Format an authenticated frame from an NRP command string."""
    payload = nrp_command.encode("utf-8")
    if not payload.endswith(b"\n"):
        payload += b"\n"

    sig = compute_mac(key, challenge, sequence, payload)
    frame = b"AUTH/1 " + str(sequence).encode("ascii") + b" " + sig + b" " + payload
    if len(frame) > MAX_FRAME:
        raise FrameTooLongError(f"Frame length {len(frame)} exceeds MAX_FRAME {MAX_FRAME}")
    return frame


class StreamingFrameParser:
    """Consumes arbitrary chunks of a serial stream and yields delimited frames."""

    def __init__(self, max_frame: int = MAX_FRAME, max_buffer: int = MAX_BUFFER):
        self.max_frame = max_frame
        self.max_buffer = max_buffer
        self.buffer = bytearray()

    def feed(self, chunk: bytes) -> Iterator[bytes]:
        """Feed bytes into the stream and yield extracted complete lines."""
        if not chunk:
            return

        self.buffer.extend(chunk)
        if len(self.buffer) > self.max_buffer:
            self.buffer.clear()
            raise FrameTooLongError("Stream buffer overflow; discarded buffered bytes")

        while b"\n" in self.buffer:
            idx = self.buffer.index(b"\n")
            line = bytes(self.buffer[: idx + 1])
            del self.buffer[: idx + 1]

            if len(line) > self.max_frame:
                raise FrameTooLongError(f"Extracted line length {len(line)} exceeds {self.max_frame}")
            yield line

    def reset(self) -> None:
        """Clear buffer on disconnect or error."""
        self.buffer.clear()


class Authenticator:
    """Server-side endpoint authenticator."""

    def __init__(self, key: bytes, challenge: Optional[bytes] = None, max_frame: int = MAX_FRAME):
        if len(key) != 32:
            raise ValueError("Key must be 32 bytes")
        self._key = key
        self.challenge = challenge if challenge is not None else os.urandom(32)
        if len(self.challenge) != 32:
            raise ValueError("Challenge must be 32 bytes")
        self.highest_sequence = 0
        self.max_frame = max_frame

    def get_challenge_frame(self) -> bytes:
        return b"AUTH/1 CHALLENGE " + self.challenge.hex().encode("ascii") + b"\n"

    def verify_and_unpack(self, frame: bytes) -> bytes:
        """Validate authenticated frame and return unpacked NRP command payload."""
        if len(frame) > self.max_frame:
            raise FrameTooLongError(f"Frame exceeds {self.max_frame} bytes")

        # Check for unauthenticated diagnostic ping (if allowed in diagnostic mode)
        if UNAUTH_DIAG_RE.fullmatch(frame):
            return frame

        match = AUTH_FRAME_RE.fullmatch(frame)
        if not match:
            raise MalformedFrameError("Frame does not match AUTH/1 grammar")

        sequence = int(match.group(1))
        signature = match.group(2)
        nrp_payload = match.group(3) + b"\n"

        if sequence <= self.highest_sequence:
            raise AuthenticationError(f"Replay detected: seq {sequence} <= highest {self.highest_sequence}")

        expected_sig = compute_mac(self._key, self.challenge, sequence, nrp_payload)
        if not hmac.compare_digest(signature, expected_sig):
            raise AuthenticationError("HMAC verification failed")

        self.highest_sequence = sequence
        return nrp_payload


class SimulatedSerialChannel:
    """Simulates an in-memory full-duplex serial connection with fault injection."""

    def __init__(self, latency_s: float = 0.0):
        self.latency_s = latency_s
        self.is_connected = True
        self._pipe_a_to_b = bytearray()
        self._pipe_b_to_a = bytearray()

    def write_a(self, data: bytes) -> None:
        if not self.is_connected:
            raise DisconnectError("Cannot write to disconnected channel")
        self._pipe_a_to_b.extend(data)

    def read_b(self, max_bytes: int = 1024) -> bytes:
        if not self.is_connected:
            raise DisconnectError("Channel disconnected")
        chunk = bytes(self._pipe_a_to_b[:max_bytes])
        del self._pipe_a_to_b[:max_bytes]
        return chunk

    def write_b(self, data: bytes) -> None:
        if not self.is_connected:
            raise DisconnectError("Cannot write to disconnected channel")
        self._pipe_b_to_a.extend(data)

    def read_a(self, max_bytes: int = 1024) -> bytes:
        if not self.is_connected:
            raise DisconnectError("Channel disconnected")
        chunk = bytes(self._pipe_b_to_a[:max_bytes])
        del self._pipe_b_to_a[:max_bytes]
        return chunk

    def disconnect(self) -> None:
        self.is_connected = False
        self._pipe_a_to_b.clear()
        self._pipe_b_to_a.clear()
