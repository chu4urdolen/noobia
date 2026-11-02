#!/usr/bin/env python3
"""Build short, finite NRP/1 VM checks for Lynx camera and flashlight."""

from pathlib import Path
import struct

OUT = Path(__file__).resolve().parent.parent / "programs"


def mov(register, value):
    return bytes((1, register)) + struct.pack("<i", value)


def call(destination, native, registers=()):
    return bytes((0x20, destination)) + struct.pack("<H", native) + bytes(
        (len(registers), *registers))


def save(name, program, assembly):
    if len(program) > 1024 or program[-1] != 0:
        raise ValueError("invalid finite VM program")
    OUT.mkdir(exist_ok=True)
    (OUT / f"{name}.hex").write_text(program.hex() + "\n")
    (OUT / f"{name}.asm").write_text(assembly + "\n")


save("camera_status", call(0, 394) + b"\x00",
     "# Read-only camera inventory; r0 is 0 until capture is validated.\n"
     "SYS r0, CAMERA_STATUS\nHALT")
save("flashlight_status", call(0, 391) + b"\x00",
     "# Read-only flashlight inventory; r0 is 0 until visual validation.\n"
     "SYS r0, FLASH_STATUS\nHALT")
save("flashlight_stop", call(0, 397) + b"\x00",
     "# Request OFF; the native call reports driver_present and off_verified.\n"
     "SYS r0, FLASH_STOP\nHALT")
save("flashlight_pulse_100ms", mov(0, 100) + call(1, 396, (0,)) +
     call(2, 397) + b"\x00",
     "# One bounded pulse; native call enforces the health gate and OFF.\n"
     "# A failed pulse faults the VM, so FLASH_STOP remains callable directly.\n"
     "MOVI r0, 100\nSYS r1, FLASH_PULSE, r0\nSYS r2, FLASH_STOP\nHALT")
