#!/usr/bin/env python3
"""Passive, bounded event collector and receipt validator for Lynx headset/jack status.

Strictly passive: does not write to audio routing kcontrols, sysfs, or input devices.
Enforces architectural separation between mechanical/impedance switch detection and
actual ALSA/DSP routed audio.

On OnePlus Nord 3 (CPH2493, MediaTek MT6983 Dimensity 9000), analog headset
connectivity is routed over USB Type-C via an FSA4480 / DIO4480 analog switch (I2C6 @ 0x42)
cooperating with MT6375 TCPC and MT6338 PMIC ACCDET (Accessory Detection).
"""

from dataclasses import dataclass, field
import fcntl
import json
import os
from pathlib import Path
import select
import struct
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

HEADSET_DEVICE_NAME = "mt6983-mt6338 Headset Jack"
EVIOCGSW_8 = 0x8008451B
EV_SW = 0x05

# Linux input switch constants (linux/input-event-codes.h)
SW_HEADPHONE_INSERT = 0x02
SW_MICROPHONE_INSERT = 0x04
SW_LINEOUT_INSERT = 0x06
SW_JACK_PHYSICAL_INSERT = 0x07

SWITCH_BIT_MAP = {
    "headphone": SW_HEADPHONE_INSERT,
    "microphone": SW_MICROPHONE_INSERT,
    "lineout": SW_LINEOUT_INSERT,
    "physical": SW_JACK_PHYSICAL_INSERT,
}

# Decoded accessory classifications
ACCESSORY_UNPLUGGED = "UNPLUGGED"
ACCESSORY_HEADSET_4POLE = "HEADSET_4POLE"
ACCESSORY_HEADPHONES_3POLE = "HEADPHONES_3POLE"
ACCESSORY_LINEOUT = "LINEOUT"
ACCESSORY_INVALID = "INVALID_SWITCH_STATE"

# Hardware parameters for OnePlus Nord 3 / MT6983 / MT6338 ACCDET
HARDWARE_CONFIG = {
    "soc": "MediaTek MT6983 (Dimensity 9000)",
    "pmic_accdet": "MT6338 ACCDET",
    "typec_switch": "FSA4480 / DIO4480 (I2C6 @ 0x42)",
    "hs_det_gpio": 98,
    "auxadc_channel": "AUXADC_ACCDET",
    "three_key_thresholds_mv": [0, 82, 170, 306],
    "three_key_thresholds_cdd_mv": [0, 121, 192, 600],
    "four_key_thresholds_mv": [0, 58, 121, 192, 400],
}

# 64-bit struct input_event: timeval (16 bytes: 2x 64-bit longs), type (uint16), code (uint16), value (int32) -> 24 bytes
INPUT_EVENT_STRUCT_64 = "qqHHi"
INPUT_EVENT_SIZE_64 = struct.calcsize(INPUT_EVENT_STRUCT_64)


@dataclass
class HeadsetEvaluationVerdict:
    status: str  # "PASS_DETECTED", "PASS_UNPLUGGED", "FAILED", "ABSENT"
    is_valid: bool
    jack_detected: bool
    accessory_type: str
    routed_audio_validated: bool
    summary: str
    details: Dict[str, Any] = field(default_factory=dict)
    failures: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "is_valid": self.is_valid,
            "jack_detected": self.jack_detected,
            "accessory_type": self.accessory_type,
            "routed_audio_validated": self.routed_audio_validated,
            "summary": self.summary,
            "details": self.details,
            "failures": self.failures,
        }


def parse_switch_bits(bits: int) -> Dict[str, bool]:
    """Convert bitmask from EVIOCGSW into named boolean switch states."""
    return {name: bool(bits & (1 << bit)) for name, bit in SWITCH_BIT_MAP.items()}


def decode_accessory_type(switches: Dict[str, bool]) -> str:
    """Decode input switch states into high-level accessory classification.

    On Nord 3 / MT6338:
    - UNPLUGGED: physical=False, all false.
    - HEADSET_4POLE: physical=True, headphone=True, microphone=True, lineout=False.
    - HEADPHONES_3POLE: physical=True, headphone=True, microphone=False, lineout=False.
    - LINEOUT: physical=True, lineout=True, headphone=False, microphone=False.
    - INVALID: Any illegal permutation (e.g. physical=False but active pins, or simultaneous headphone+lineout).
    """
    phys = switches.get("physical", False)
    hp = switches.get("headphone", False)
    mic = switches.get("microphone", False)
    line = switches.get("lineout", False)

    if not phys:
        if hp or mic or line:
            return ACCESSORY_INVALID
        return ACCESSORY_UNPLUGGED

    # Physical insertion asserted:
    if hp and line:
        return ACCESSORY_INVALID

    if hp and mic and not line:
        return ACCESSORY_HEADSET_4POLE

    if hp and not mic and not line:
        return ACCESSORY_HEADPHONES_3POLE

    if line and not hp and not mic:
        return ACCESSORY_LINEOUT

    return ACCESSORY_INVALID


def find_headset_input_device(sysfs_input: Path = Path("/sys/class/input")) -> Optional[str]:
    """Scan sysfs to find the event device associated with mt6983-mt6338 Headset Jack."""
    if not sysfs_input.exists():
        return None
    for entry in sorted(sysfs_input.glob("event*")):
        name_file = entry / "device/name"
        if name_file.exists():
            try:
                if name_file.read_text().strip() == HEADSET_DEVICE_NAME:
                    return entry.name
            except OSError:
                continue
    return None


def read_switches_from_fd(fd: int) -> int:
    """Read switch bitmask using read-only ioctl EVIOCGSW."""
    buf = bytearray(8)
    fcntl.ioctl(fd, EVIOCGSW_8, buf, True)
    return int.from_bytes(buf, "little")


def read_current_switches(event_path: Path) -> Tuple[Optional[Dict[str, bool]], Optional[str]]:
    """Open event device in non-blocking read-only mode and query switch states."""
    if not event_path.exists():
        return None, "device_node_not_found"
    try:
        fd = os.open(event_path, os.O_RDONLY | os.O_NONBLOCK)
    except OSError as exc:
        return None, f"open_error_{type(exc).__name__}"
    try:
        bits = read_switches_from_fd(fd)
        return parse_switch_bits(bits), None
    except OSError as exc:
        return None, f"ioctl_error_{type(exc).__name__}"
    finally:
        os.close(fd)


def collect_bounded_events(
    event_path: Path,
    timeout_seconds: float = 5.0,
    max_events: int = 10,
) -> Dict[str, Any]:
    """Passively listen for EV_SW input events up to timeout_seconds without blocking indefinitely."""
    receipt: Dict[str, Any] = {
        "device_node": str(event_path),
        "device_name": HEADSET_DEVICE_NAME,
        "timeout_seconds": timeout_seconds,
        "events_captured": [],
        "initial_switches": None,
        "final_switches": None,
        "collection_completed": False,
        "error": None,
    }

    if not event_path.exists():
        receipt["error"] = "device_node_not_found"
        return receipt

    try:
        fd = os.open(event_path, os.O_RDONLY | os.O_NONBLOCK)
    except OSError as exc:
        receipt["error"] = f"open_error_{type(exc).__name__}"
        return receipt

    try:
        # Read initial switch state
        initial_bits = read_switches_from_fd(fd)
        receipt["initial_switches"] = parse_switch_bits(initial_bits)

        deadline = time.monotonic() + timeout_seconds
        events = []

        while time.monotonic() < deadline and len(events) < max_events:
            remaining = max(0.0, deadline - time.monotonic())
            rlist, _, _ = select.select([fd], [], [], min(remaining, 0.5))
            if not rlist:
                continue

            try:
                raw_data = os.read(fd, INPUT_EVENT_SIZE_64 * 4)
            except (BlockingIOError, InterruptedError):
                continue
            except OSError as exc:
                receipt["error"] = f"read_error_{type(exc).__name__}"
                break

            if not raw_data:
                break

            # Parse input_event packets
            offset = 0
            while offset + INPUT_EVENT_SIZE_64 <= len(raw_data):
                sec, usec, ev_type, code, val = struct.unpack_from(
                    INPUT_EVENT_STRUCT_64, raw_data, offset
                )
                offset += INPUT_EVENT_SIZE_64
                if ev_type == EV_SW:
                    matched_name = next(
                        (k for k, v in SWITCH_BIT_MAP.items() if v == code),
                        f"unknown_sw_{code}",
                    )
                    events.append(
                        {
                            "sec": sec,
                            "usec": usec,
                            "type": "EV_SW",
                            "code": code,
                            "switch": matched_name,
                            "value": val,
                        }
                    )

        # Read final switch state
        final_bits = read_switches_from_fd(fd)
        receipt["final_switches"] = parse_switch_bits(final_bits)
        receipt["events_captured"] = events
        receipt["collection_completed"] = True
    except OSError as exc:
        receipt["error"] = f"ioctl_error_{type(exc).__name__}"
    finally:
        os.close(fd)

    return receipt


def evaluate_headset_receipt(receipt: Optional[Dict[str, Any]]) -> HeadsetEvaluationVerdict:
    """Evaluate a headset inventory or event capture receipt with strict diagnostic separation."""
    if not receipt:
        return HeadsetEvaluationVerdict(
            status="ABSENT",
            is_valid=False,
            jack_detected=False,
            accessory_type=ACCESSORY_UNPLUGGED,
            routed_audio_validated=False,
            summary="Receipt data is missing or empty",
            failures=["missing_receipt"],
        )

    failures: List[str] = []
    details: Dict[str, Any] = {}

    # Support either passive status inventory format or bounded event collector format
    switches = None
    if "switches" in receipt:
        switches = receipt["switches"]
    elif "final_switches" in receipt and receipt["final_switches"] is not None:
        switches = receipt["final_switches"]
    elif "initial_switches" in receipt and receipt["initial_switches"] is not None:
        switches = receipt["initial_switches"]
    elif "evidence" in receipt and "switches" in receipt["evidence"]:
        switches = receipt["evidence"]["switches"]

    if switches is None:
        failures.append("no_switch_state_found_in_receipt")
    elif not isinstance(switches, dict):
        failures.append("switches_field_not_dict")
    else:
        # Validate that standard switch keys are present
        for key in ("headphone", "microphone", "lineout", "physical"):
            if key not in switches:
                failures.append(f"missing_switch_key_{key}")

    if receipt.get("error"):
        failures.append(f"receipt_reported_error: {receipt['error']}")

    jack_inserted = False
    accessory_type = ACCESSORY_UNPLUGGED
    if switches and isinstance(switches, dict):
        accessory_type = decode_accessory_type(switches)
        if accessory_type == ACCESSORY_INVALID:
            failures.append("invalid_switch_combination")
        jack_inserted = switches.get("physical", False) or bool(
            switches.get("headphone")
            or switches.get("microphone")
            or switches.get("lineout")
        )

    # Architectural Boundary: Jack detection does NOT validate routed audio!
    routed_audio_validated = False
    details["architectural_boundary"] = (
        "Jack switch detection validates mechanical/impedance sense only; "
        "it does NOT validate ALSA PCM routing, DSP streaming, DAC enablement, or acoustic output."
    )
    details["switches"] = switches
    details["jack_detected"] = jack_inserted
    details["accessory_type"] = accessory_type
    details["hardware_config"] = HARDWARE_CONFIG

    if "typec_mux" in receipt:
        details["typec_mux"] = receipt["typec_mux"]

    if failures:
        return HeadsetEvaluationVerdict(
            status="FAILED",
            is_valid=False,
            jack_detected=jack_inserted,
            accessory_type=accessory_type,
            routed_audio_validated=False,
            summary=f"Headset evaluation failed with {len(failures)} error(s)",
            details=details,
            failures=failures,
        )

    status_str = "PASS_DETECTED" if jack_inserted else "PASS_UNPLUGGED"
    summary_str = (
        f"Headset jack switch state valid: {accessory_type} "
        f"(routed audio correctly unvalidated)"
    )

    return HeadsetEvaluationVerdict(
        status=status_str,
        is_valid=True,
        jack_detected=jack_inserted,
        accessory_type=accessory_type,
        routed_audio_validated=False,
        summary=summary_str,
        details=details,
        failures=[],
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Passive bounded collector & validator for Lynx headset status"
    )
    parser.add_argument(
        "--validate",
        type=Path,
        help="Validate an existing receipt JSON file",
    )
    parser.add_argument(
        "--listen",
        action="store_true",
        help="Passively listen for bounded switch events on local/host input node",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Listening timeout in seconds (default: 5.0)",
    )
    args = parser.parse_args()

    if args.validate:
        if not args.validate.exists():
            print(f"Error: file not found {args.validate}", file=sys.stderr)
            sys.exit(2)
        data = json.loads(args.validate.read_text())
        verdict = evaluate_headset_receipt(data)
        print(json.dumps(verdict.to_dict(), indent=2))
        sys.exit(0 if verdict.is_valid else 1)

    if args.listen:
        event_name = find_headset_input_device()
        if not event_name:
            print(
                json.dumps(
                    {"error": f"Device '{HEADSET_DEVICE_NAME}' not found in sysfs"},
                    indent=2,
                )
            )
            sys.exit(1)
        receipt = collect_bounded_events(
            Path("/dev/input") / event_name, timeout_seconds=args.timeout
        )
        print(json.dumps(receipt, indent=2))
        sys.exit(0)

    parser.print_help()


if __name__ == "__main__":
    main()
