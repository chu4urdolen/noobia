#!/usr/bin/env python3
"""Move one Lolth servo 30 degrees toward its factory reference and detach."""

import argparse
import time

from lolthctl import DEFAULT_HOST, request


FACTORY_ZERO = (135, 45, 135, 45, 45, 135, 45, 135)


def call(command: str) -> None:
    answer = request(DEFAULT_HOST, 4242, command)
    print(answer, flush=True)
    if answer.startswith("NRP/1 1 ERR "):
        raise RuntimeError(answer)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("servo", type=int, choices=range(1, 9), metavar="1..8")
    args = parser.parse_args()
    servo = args.servo
    direction = 1 if FACTORY_ZERO[servo - 1] > 90 else -1
    print(f"SERVO {servo}: 90 -> {90 + 30 * direction} -> 90", flush=True)
    try:
        call(f"CALL SERVO_ARM {servo} 90")
        for step in range(5, 31, 5):
            call(f"CALL SERVO_SET {servo} {90 + direction * step}")
            time.sleep(0.2)
        time.sleep(2)
        for step in range(25, -1, -5):
            call(f"CALL SERVO_SET {servo} {90 + direction * step}")
            time.sleep(0.2)
        # Let the joint reach 90 degrees before removing holding torque.
        time.sleep(2)
    finally:
        call("CALL SERVO_DETACH_ALL")


if __name__ == "__main__":
    main()
