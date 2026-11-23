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
- tilt crosses 45 degrees and holds 30 s: NOOBIA P1 motion position.change to=horizontal|vertical from=... tilt=N
- every 60 samples:                       NOOBIA P0 motion status.sample orientation=... x=... y=... z=...

Gestures (G3, Gwyn 2026-11-23), from a ~1 s burst of 12.5 Hz samples read
straight from ``lynx-hf-sample`` (same sensor-on time as the single read):
- motion.freefall  >= 2 samples in a row below 0.35 g          (a drop)
- motion.shaken    >= 4 samples over 0.5 g from 1 g, both ways
- motion.pickup    clear movement after resting >= 60 s
- motion.placed    still again for >= 15 s after being moved
- motion.rocked    tilt swinging 0.3-1.2 Hz, 6-60 degrees, over ~8 s
Each gesture has a cooldown; the short history is volatile (RAM) state.
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
DEFAULT_HF_SAMPLE = "/usr/local/bin/lynx-hf-sample"
BURST_SECONDS = 1.0
BURST_EVENTS = 12
G_MM = 9807                        # 1 g in the driver's raw unit (mm/s^2, gain 1000)
FREEFALL_G = 0.35
SHAKE_DEV_G = 0.5
SHAKE_SAMPLES = 4
STILL_JITTER_MM = 250              # burst spread below this = still
MOVE_JITTER_MM = 1200              # burst spread above this = clearly moving
REST_BEFORE_PICKUP_S = 60
STILL_BEFORE_PLACED_S = 15
ROCK_WINDOW_S = 8.0
ROCK_MIN_AMPL_DEG, ROCK_MAX_AMPL_DEG = 6.0, 60.0
ROCK_MIN_HZ, ROCK_MAX_HZ = 0.3, 1.2
COOLDOWN_S = {"freefall": 10, "shaken": 30, "rocked": 60, "pickup": 20, "placed": 20}
MOTION_SAMPLE_EVERY = 60          # a P0 status sample about once a minute at 1 Hz
POSITION_DEBOUNCE_S = 30


def tilt_degrees(x: int, y: int, z: int) -> float:
    """Angle between the screen normal and vertical gravity: 0 = flat, 90 = upright."""
    import math
    g = math.sqrt(x * x + y * y + z * z)
    if g <= 0:
        return 0.0
    return math.degrees(math.acos(min(1.0, abs(z) / g)))


def read_motion_sensor(bin_path: str = DEFAULT_MOTION_BIN) -> dict:
    cmd = os.environ.get("LYNX_MOTION_BIN", bin_path)
    res = subprocess.run([cmd], input=b'{"choice": "accel"}\n', capture_output=True, timeout=5, check=True)
    return json.loads(res.stdout)


def read_motion_burst(bin_path: str = DEFAULT_HF_SAMPLE) -> dict:
    """{"raw": last [x,y,z], "burst": [[t_s, x, y, z], ...]} from one bounded burst."""
    cmd = os.environ.get("LYNX_HF_SAMPLE_BIN", bin_path)
    res = subprocess.run(["/usr/bin/python3", cmd, "--sensor", "1", "--seconds", str(BURST_SECONDS),
                          "--events", str(BURST_EVENTS)], capture_output=True, timeout=4, check=True)
    doc = json.loads(res.stdout)
    if doc.get("sensor_type") != 1 or doc.get("disabled") is not True:
        raise ValueError("accelerometer burst not confirmed disabled")
    burst = []
    for e in doc.get("events") or []:
        xyz = e.get("raw_xyz")
        if (isinstance(xyz, list) and len(xyz) == 3 and all(type(v) is int and abs(v) <= 100000 for v in xyz)):
            burst.append([int(e.get("timestamp_ns", 0)) / 1e9] + xyz)
    if not burst:
        raise ValueError("accelerometer burst empty")
    return {"raw": burst[-1][1:], "burst": burst}


def read_motion(reader=None) -> dict:
    """The burst, or the old single read if the burst helper is missing."""
    if reader is not None:
        return reader()
    try:
        return read_motion_burst()
    except (OSError, ValueError, subprocess.SubprocessError):
        return read_motion_sensor()


def _mag(x, y, z) -> float:
    return (x * x + y * y + z * z) ** 0.5


def burst_features(burst: list) -> dict:
    """Freefall, shake and movement measures for one burst of [t, x, y, z]."""
    mags = [_mag(x, y, z) / G_MM for _, x, y, z in burst]
    low_run = best = 0
    for m in mags:
        low_run = low_run + 1 if m < FREEFALL_G else 0
        best = max(best, low_run)
    devs = [m - 1.0 for m in mags]
    big = [d for d in devs if abs(d) > SHAKE_DEV_G]
    n = len(burst)
    mean = [sum(v[i] for v in burst) / n for i in (1, 2, 3)]
    jitter = max(_mag(*(v[i] - mean[i - 1] for i in (1, 2, 3))) for v in burst)
    return {
        "freefall": best >= 2,
        "shaken": len(big) >= SHAKE_SAMPLES and any(d > 0 for d in big) and any(d < 0 for d in big),
        "jitter": jitter,
    }


def rocking(tilts: list) -> tuple[bool, float, float]:
    """(rocked, frequency Hz, peak-to-peak degrees) over a [t, tilt] history."""
    if len(tilts) < 12 or tilts[-1][0] - tilts[0][0] < ROCK_WINDOW_S * 0.75:
        return False, 0.0, 0.0
    values = [v for _, v in tilts]
    mean = sum(values) / len(values)
    ampl = max(values) - min(values)
    crossings = []
    prev = values[0] - mean
    for (t, v) in tilts[1:]:
        cur = v - mean
        if (prev < -1.0 and cur >= -1.0 and cur > 0) or (prev > 1.0 and cur <= 1.0 and cur < 0):
            crossings.append(t)
        if abs(cur) > 1.0:
            prev = cur
    span = tilts[-1][0] - tilts[0][0]
    hz = (len(crossings) / 2.0) / span if span > 0 else 0.0
    ok = (ROCK_MIN_AMPL_DEG <= ampl <= ROCK_MAX_AMPL_DEG and ROCK_MIN_HZ <= hz <= ROCK_MAX_HZ
          and len(crossings) >= 4)
    return ok, hz, ampl


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
        data = read_motion(reader)
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

    # Position (Tom, 2026-11-22): sampled about once a second; reported only
    # when the tilt from flat crosses 45 degrees (horizontal <-> vertical) and
    # the new position has held for POSITION_DEBOUNCE_S. Wobbling around 45
    # degrees, or a brief pick-up, produces nothing.
    tilt = tilt_degrees(rx, ry, rz)
    position = "horizontal" if tilt < 45.0 else "vertical"
    reported = state.get("position")
    candidate, since = state.get("candidate"), state.get("candidate_since")
    if reported is None:
        reported = position  # first sample sets the baseline, says nothing
        candidate, since = None, None
    elif position == reported:
        candidate, since = None, None
    elif candidate != position:
        candidate, since = position, t
    elif t - int(since or t) >= POSITION_DEBOUNCE_S:
        line = emit_line(
            sense, 1, "motion", "position.change",
            fields={"to": position, "from": reported, "tilt": int(round(tilt))},
            text=f"Lynx is now {position} (tilt {int(round(tilt))} degrees)",
            dry_run=dry_run,
        )
        emitted.append(line)
        reported, candidate, since = position, None, None

    # ---- gestures (G3) --------------------------------------------------
    burst = data.get("burst") or []
    cool = dict(state.get("cooldown") or {})
    activity = state.get("activity") or "unknown"      # resting | moving | unknown
    still_since = state.get("still_since")
    tilts = [p for p in (state.get("tilts") or []) if t - p[0] <= ROCK_WINDOW_S]
    gestures = []

    def gesture(kind, text, **fields):
        if t < float(cool.get(kind, 0)):
            return
        cool[kind] = t + COOLDOWN_S[kind]
        gestures.append(kind)
        emitted.append(emit_line(sense, 1, "motion", kind, fields=fields, text=text, dry_run=dry_run))

    if burst:
        f = burst_features(burst)
        t0 = burst[0][0]
        for bt, x, y, z in burst:   # burst times are sensor clock; place them in wall time
            tilts.append([round(t - (burst[-1][0] - bt), 2), round(tilt_degrees(x, y, z), 1)])
        tilts = [p for p in tilts if t - p[0] <= ROCK_WINDOW_S][-120:]
        del t0
        if f["freefall"]:
            gesture("freefall", "Lynx is falling (free fall)")
        if f["shaken"]:
            gesture("shaken", "Lynx is being shaken")
        moving = f["jitter"] >= MOVE_JITTER_MM or f["shaken"]
        still = f["jitter"] < STILL_JITTER_MM
        if moving:
            if activity == "resting":
                gesture("pickup", "Lynx was picked up", to=current_orient)
            activity, still_since = "moving", None
        elif still:
            still_since = still_since if still_since is not None else t
            if t - still_since >= STILL_BEFORE_PLACED_S and activity == "moving":
                gesture("placed", "Lynx was put down and rests", to=current_orient)
                activity = "settling"
            if t - still_since >= REST_BEFORE_PICKUP_S:
                activity = "resting"
        rocked, hz, ampl = rocking(tilts)
        if rocked and not f["shaken"]:
            gesture("rocked", "Lynx is being rocked gently", hz=round(hz, 2), degrees=int(round(ampl)))

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
        "position": reported,
        "candidate": candidate,
        "candidate_since": since,
        "last_ts": t,
        "activity": activity,
        "still_since": still_since,
        "cooldown": {k: v for k, v in cool.items() if float(v) > t},
        "tilts": tilts,
    }
    if not dry_run:
        save_state(path, new_state)

    result = base_result("motion", emitted=emitted, dry_run=dry_run)
    result.update({
        "orientation": current_orient,
        "position": reported,
        "tilt": round(tilt, 1),
        "raw": [rx, ry, rz],
        "samples": samples,
        "activity": activity,
        "gestures": gestures,
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
