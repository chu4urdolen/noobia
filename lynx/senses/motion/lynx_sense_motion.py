#!/usr/bin/env python3
"""S9 motion/orientation sense for Lynx: accelerometer (BMI260/BMI2XY).

Sampled sense. Data source: ``/usr/local/bin/lynx-motion-read`` (or $LYNX_MOTION_BIN).
Expects JSON stdin ({"choice": "accel"}) and returns:
{"choice":"accel","sensor":"bmi2xy acc","raw":[x, y, z], "gain":1000, ...}

Raw gravity vector:
- flat on table (screen up): z ~ +9800 mG
- flat face down: z ~ -9800 mG
- held upright in portrait: y ~ +9800 mG (or -9800)
- tilted landscape: x ~ +/-9800 mG

Events:
- transition from flat to upright/held: NOOBIA P1 motion pickup orientation=... from=...
- transition from upright/held to flat: NOOBIA P1 motion placed orientation=... from=...
- general orientation change:          NOOBIA P1 motion orientation.change to=... from=...
- every 15 samples:                    NOOBIA P0 motion status.sample orientation=... x=... y=... z=...
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from lynx_senses_lib import (  # noqa: E402
    SenseUnavailable,
    base_result,
    emit_line,
    failure,
    finish,
    import_sense,
    load_state,
    now_ts,
    save_state,
    state_path,
)

DEFAULT_MOTION_BIN = "/usr/local/bin/lynx-motion-read"
MOTION_SAMPLE_EVERY = 15


def read_motion_sensor(bin_path: str = DEFAULT_MOTION_BIN) -> dict:
    cmd = os.environ.get("LYNX_MOTION_BIN", bin_path)
    res = subprocess.run([cmd], input=b'{"choice": "accel"}\n', capture_output=True, timeout=5, check=True)
    return json.loads(res.stdout)


def classify_orientation(x: int, y: int, z: int) -> str:
    abs_x = abs(x)
    abs_y = abs(y)
    abs_z = abs(z)

    if abs_z > abs_x and abs_z > abs_y:
        if z > 2500:
            return "flat_up"
        if z < -2500:
            return "flat_down"
    elif abs_y > abs_x:
        if y > 2500:
            return "portrait"
        if y < -2500:
            return "inverted"
    else:
        if x > 2500:
            return "landscape_left"
        if x < -2500:
            return "landscape_right"
    return "tilted"


def run(dry_run: bool = False, state_file: str | None = None,
        reader=None, now: int | None = None) -> tuple[dict, int]:
    t = int(now if now is not None else now_ts())
    try:
        sense = import_sense()
    except SenseUnavailable as exc:
        return failure("motion", exc)

    try:
        data = (reader or read_motion_sensor)()
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return failure("motion", exc)

    raw_list = data.get("raw") or []
    if len(raw_list) < 3:
        return failure("motion", ValueError("malformed raw motion sensor data"))
    rx, ry, rz = int(raw_list[0]), int(raw_list[1]), int(raw_list[2])

    current_orient = classify_orientation(rx, ry, rz)
    path = state_path("motion", state_file)
    state = load_state(path)
    emitted: list[str] = []
    samples = int(state.get("samples", 0)) + 1
    prev_orient = state.get("orientation")

    if prev_orient is None:
        # First sample sets baseline
        pass
    elif current_orient != prev_orient:
        if prev_orient in ("flat_up", "flat_down") and current_orient in ("portrait", "landscape_left", "landscape_right", "tilted"):
            event = "pickup"
            text = f"Lynx was picked up into {current_orient} (from {prev_orient})"
        elif prev_orient in ("portrait", "landscape_left", "landscape_right", "tilted") and current_orient in ("flat_up", "flat_down"):
            event = "placed"
            text = f"Lynx was placed down ({current_orient}) (from {prev_orient})"
        else:
            event = "orientation.change"
            text = f"Lynx orientation changed to {current_orient} (from {prev_orient})"

        line = emit_line(
            sense,
            1,
            "motion",
            event,
            fields={"to": current_orient, "from": prev_orient, "x": rx, "y": ry, "z": rz},
            text=text,
            dry_run=dry_run,
        )
        emitted.append(line)

    if samples % MOTION_SAMPLE_EVERY == 0:
        line = emit_line(
            sense,
            0,
            "motion",
            "status.sample",
            fields={"orientation": current_orient, "x": rx, "y": ry, "z": rz},
            text=f"Motion sample orientation={current_orient}",
            dry_run=dry_run,
        )
        emitted.append(line)

    new_state = {
        "samples": samples,
        "orientation": current_orient,
        "last_raw": [rx, ry, rz],
        "last_ts": t,
    }
    if not dry_run:
        save_state(path, new_state)

    result = base_result("motion", emitted=emitted, dry_run=dry_run)
    result.update({
        "orientation": current_orient,
        "raw": [rx, ry, rz],
        "samples": samples,
    })
    return result, 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    res, code = run(dry_run=args.dry_run)
    return finish(res, code)


if __name__ == "__main__":
    main()
