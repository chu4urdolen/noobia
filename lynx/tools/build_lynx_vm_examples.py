#!/usr/bin/env python3
"""Build tiny NRP/1 VM programs for Lynx's haptic and image sequences."""

from pathlib import Path
import struct

OUT = Path(__file__).resolve().parent.parent / "programs"


def mov(register, value):
    return bytes([1, register]) + struct.pack("<i", value)


def mixed_sys(destination, function, registers, text=b""):
    return bytes([0x22, destination]) + struct.pack("<H", function) + bytes(
        [len(registers), *registers, len(text)]) + text


def sys_call(destination, function):
    return bytes([0x20, destination]) + struct.pack("<H", function) + b"\x00"


def example(name, values, description):
    program = b"".join(mov(i, v) for i, v in enumerate(values))
    program += mixed_sys(0, 3, list(range(len(values))))
    program += sys_call(0, 4) + b"\x00"
    if len(program) > 1024:
        raise ValueError("VM program too large")
    OUT.mkdir(exist_ok=True)
    (OUT / f"{name}.hex").write_text(program.hex() + "\n")
    (OUT / f"{name}.asm").write_text(description + "\n")


example("haptic_two_pulses",
        [0, 200, 300, 4, 0b1010, 1, 80],
        """# Common VM v1; CALL_MIXED SEQUENCE_SET 0 200 HAPTIC_SET 4 1010 append=1 duration=80ms.
# Four positions: pulse, stop, pulse, stop. Finite; motor off at completion.
MOVI r0, 0
MOVI r1, 200
MOVI r2, 300
MOVI r3, 4
MOVI r4, 0b1010
MOVI r5, 1
MOVI r6, 80
SYS_MIXED r0, SEQUENCE_SET, r0..r6, ""
SYS r0, SEQUENCE_START
HALT""")

example("image_talk_sequence",
        [0, 500, 311, 4, 0b1010, 1, 0, 1],
        """# Common VM v1; CALL_MIXED SEQUENCE_SET 0 500 IMAGE_CHOOSE 4 1010 append=1 poses=(0,1).
# Pose index 0 is standing; 1 is talking in the current sorted catalog.
MOVI r0, 0
MOVI r1, 500
MOVI r2, 311
MOVI r3, 4
MOVI r4, 0b1010
MOVI r5, 1
MOVI r6, 0
MOVI r7, 1
SYS_MIXED r0, SEQUENCE_SET, r0..r7, ""
SYS r0, SEQUENCE_START
HALT""")
