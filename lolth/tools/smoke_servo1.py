#!/usr/bin/env python3
"""Bounded servo-1 excursion; always request detach at the end."""

import argparse
import time

from lolthctl import DEFAULT_HOST, request


HOST = DEFAULT_HOST
PORT = 4242


def call(command: str) -> None:
    answer = request(HOST, PORT, command)
    print(answer, flush=True)
    if answer.startswith("NRP/1 1 ERR "):
        raise RuntimeError(answer)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--excursion", type=int, choices=range(1, 31),
                        metavar="1..30", default=2)
    parser.add_argument("--hold", type=float, default=0.4)
    args = parser.parse_args()
    if not 0 <= args.hold <= 5:
        parser.error("--hold must be between 0 and 5 seconds")

    target = 90 + args.excursion
    try:
        call("CALL SERVO_ARM 1 90")
        current = 90
        while current < target:
            current = min(current + 5, target)
            call(f"CALL SERVO_SET 1 {current}")
            time.sleep(0.2)
        time.sleep(args.hold)
        while current > 90:
            current = max(current - 5, 90)
            call(f"CALL SERVO_SET 1 {current}")
            time.sleep(0.2)
        call("CALL SERVO_STATE 1")
    finally:
        call("CALL SERVO_DETACH_ALL")


if __name__ == "__main__":
    main()
