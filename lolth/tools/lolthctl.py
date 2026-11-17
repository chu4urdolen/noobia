#!/usr/bin/env python3
"""Send NRP/1 commands to Lolth's Wi-Fi TCP transport."""

import argparse
from pathlib import Path
import socket
import sys

DEFAULT_HOST = "192.168.4.1"


def request(host: str, port: int, command: str) -> str:
    frame = f"NRP/1 1 {command.strip()}\n".encode("ascii")
    with socket.create_connection((host, port), timeout=3) as connection:
        connection.settimeout(3)
        connection.sendall(frame)
        with connection.makefile("rb") as stream:
            while True:
                line = stream.readline()
                if not line:
                    raise ConnectionError("Lolth closed the connection without a reply")
                answer = line.decode("utf-8", errors="replace").strip()
                if answer.startswith("NRP/1 1 "):
                    return answer


def command_from_words(words: list[str]) -> str:
    if not words:
        return "INFO"
    name = words[0].lower()
    if name in ("info", "caps", "ping") and len(words) == 1:
        return name.upper()
    if name == "distance" and len(words) == 1:
        return "CALL DISTANCE_MM"
    if name == "stop" and len(words) == 1:
        return "CALL SERVO_DETACH_ALL"
    if name == "wiggle" and len(words) == 1:
        return "CALL SERVO1_WIGGLE"
    if name == "load" and len(words) == 2:
        program = bytes.fromhex(Path(words[1]).read_text(encoding="ascii"))
        if not 1 <= len(program) <= 1024:
            raise ValueError("VM program must be 1..1024 bytes")
        return f"LOAD {program.hex()}"
    if name in ("arm", "set") and len(words) == 3:
        return f"CALL SERVO_{name.upper()} {int(words[1])} {int(words[2])}"
    if name in ("state", "detach") and len(words) == 2:
        return f"CALL SERVO_{name.upper()} {int(words[1])}"
    if name in ("up", "down") and len(words) in (2, 3):
        servo = int(words[1])
        if servo < 1 or servo > 8:
            raise ValueError("servo must be 1..8")
        degrees = int(words[2]) if len(words) == 3 else 5
        return f"CALL SERVO{servo}_{name.upper()} {degrees}"
    if name == "raw" and len(words) > 1:
        return " ".join(words[1:])
    raise ValueError("unknown command; try info, caps, distance, arm, up, down, set, state, detach, stop, wiggle, load, or raw")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=4242)
    parser.add_argument("words", nargs="*")
    args = parser.parse_args()
    try:
        answer = request(args.host, args.port, command_from_words(args.words))
        print(answer)
        return 1 if answer.startswith("NRP/1 1 ERR ") else 0
    except (OSError, ValueError, UnicodeError) as error:
        print(f"lolthctl: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
