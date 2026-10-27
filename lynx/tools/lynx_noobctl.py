#!/usr/bin/env python3
"""Send one NRP/1 command to Lynx, with Iris-compatible line framing."""

import argparse
from pathlib import Path
import socket
import sys

IP = "192.168.100.107"
PORT = 4243


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="+",
                        help='e.g. PING, CALL HAPTIC_SET 80 1, or LOAD @program.hex')
    args = parser.parse_args()
    words = args.command
    if words[0].upper() == "LOAD" and len(words) == 2 and words[1].startswith("@"):
        words = ["LOAD", Path(words[1][1:]).read_text().strip()]
    command = " ".join(words)
    if "\n" in command or "\r" in command or len(command) > 4090:
        parser.error("request must be one bounded line")
    with socket.create_connection((IP, PORT), timeout=4) as conn:
        conn.settimeout(4)
        conn.sendall(f"NRP/1 1 {command}\n".encode("ascii"))
        reply = bytearray()
        while b"\n" not in reply and len(reply) < 4096:
            chunk = conn.recv(4096)
            if not chunk:
                break
            reply.extend(chunk)
    answer = reply.split(b"\n", 1)[0].decode("ascii", errors="replace")
    print(answer)
    if not answer.startswith("NRP/1 1 OK"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
