#!/usr/bin/env python3
"""JSON‑stdin reader for the AKM09918 magnetometer.

The helper mirrors the behaviour of :mod:`lynx.tools.lynx_proximity_read`
but for the magnetometer.  It validates the environment, invokes the
``lynx-hf-sample`` command, and performs the same rigorous checks as the
original code, returning a minimal JSON payload.

The function is designed to be used by the Lynx agent; it never touches
hardware directly – all device interaction is mediated through
``subprocess.run`` and the ``/dev/hf_manager`` / ``/proc/hf_manager`` files.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
import subprocess

SENSOR = "akm09918 mag"
HELPER = "/usr/local/bin/lynx-hf-sample"


def read_request() -> None:
    """Validate the JSON‑stdin request.

    The caller must provide an empty JSON object.  The input size is capped at
    4096 bytes to guard against accidental large payloads.
    """

    raw = sys.stdin.read(4097)
    if len(raw) > 4096 or json.loads(raw) != {}:
        raise ValueError("expected an empty JSON object")


def read_mag() -> dict:
    """Read a magnetometer sample and return a minimal JSON payload.

    The function performs the following steps:

    1. Confirm the device node exists and the sensor is registered.
    2. Invoke the bounded helper with ``--sensor 2``.
    3. Validate the returned JSON structure – sensor type, disabled flag,
       sensor name, gain, and at least one event.
    4. Extract the last ``raw_xyz`` entry and ensure it contains three
       integers with absolute value <= 100 000 000.
    5. Return a dictionary suitable for the agent JSON‑stdin protocol.
    """

    if (
        not Path("/dev/hf_manager").is_char_device()
        or SENSOR not in Path("/proc/hf_manager").read_text()
    ):
        raise RuntimeError("magnetometer sensor unavailable")

    result = subprocess.run(
        [
            "/usr/bin/python3",
            HELPER,
            "--sensor",
            "2",
            "--seconds",
            "1",
            "--events",
            "3",
        ],
        capture_output=True,
        text=True,
        timeout=3,
    )
    if result.returncode:
        raise RuntimeError("magnetometer sample failed")

    sample = json.loads(result.stdout)
    info = sample.get("info", {})
    events = sample.get("events", [])
    # The bounded helper may return 1–3 events within its one‑second window.
    # Therefore we only require a non‑empty events list.  The last event is
    # considered the sample.
    if (
        sample.get("sensor_type") != 2
        or not sample.get("disabled")
        or info.get("name") != SENSOR
        or info.get("gain") != 1000
        or not events
    ):
        raise RuntimeError("magnetometer sample invalid")

    raw = events[-1].get("raw_xyz")
    if (
        not isinstance(raw, list)
        or len(raw) != 3
        or any(type(v) is not int for v in raw)
        or any(abs(v) > 100_000_000 for v in raw)
    ):
        raise RuntimeError("magnetometer fields invalid")

    return {
        "sensor": SENSOR,
        "registered": True,
        "raw": raw,
        "gain": 1000,
        "unit": "driver_raw",
        "calibrated_heading": False,
        "sensor_disabled_after_sample": True,
    }


def main() -> None:
    try:
        read_request()
        print(json.dumps(read_mag(), separators=(",", ":")))
    except (OSError, ValueError, subprocess.TimeoutExpired, RuntimeError) as exc:
        print(json.dumps({"error": str(exc)}, separators=(",", ":")))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
