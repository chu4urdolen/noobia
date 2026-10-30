#!/usr/bin/env python3
"""Send one NRP/1 command to Lynx, with Iris-compatible line framing."""

import argparse
from pathlib import Path
import re
import socket
import sys

from lynx_ble_auth import envelope, load_key

IP = "192.168.100.107"
PORT = 4243
KEY_FILE = "/noobia/lynx/private/nrp-nexus.key"


def read_line(stream, limit=4096):
    received = stream.readline(limit + 1)
    if not received.endswith(b"\n") or len(received) > limit:
        raise RuntimeError("incomplete or oversized Lynx response")
    return received


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="+",
                        help='e.g. PING, CALL HAPTIC_SET 80 1, or LOAD @program.hex')
    args = parser.parse_args()
    words = args.command
    if words[0].upper() == "LOAD" and len(words) == 2 and words[1].startswith("@"):
        words = ["LOAD", Path(words[1][1:]).read_text().strip()]
    command = " ".join(words)
    if "\n" in command or "\r" in command or not command.isascii() or len(command) > 3900:
        parser.error("request must be one bounded line")
    key = load_key(KEY_FILE)
    with socket.create_connection((IP, PORT), timeout=4) as conn:
        conn.settimeout(10)
        with conn.makefile("rb") as stream:
            challenge = read_line(stream, 128)
            match = re.fullmatch(rb"AUTH/1 CHALLENGE ([0-9a-f]{64})\n", challenge)
            if not match:
                raise RuntimeError("Lynx did not present an authentication challenge")
            request = f"NRP/1 1 {command}\n".encode("ascii")
            conn.sendall(envelope(key, bytes.fromhex(match.group(1).decode()), 1,
                                  request, max_frame=4096))
            while True:
                answer = read_line(stream).decode("ascii", errors="replace").rstrip("\n")
                if not answer.startswith("NRP/1 0 EVENT "):
                    break
    print(answer)
    if not answer.startswith("NRP/1 1 OK"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
