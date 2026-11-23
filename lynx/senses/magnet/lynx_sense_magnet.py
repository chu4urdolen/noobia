#!/usr/bin/env python3
"""B3 magnetometer sense for Lynx: AK09918 3-axis magnetic flux & compass heading.

Sampled & event sense, P1/P0.
Data source: ``/usr/local/bin/lynx-magnetometer-read`` (or $LYNX_MAGNET_BIN / mocked helper).
Returns raw [x, y, z] in microteslas / driver raw units.

Events:
- Magnet detected near: total magnitude |B| >= 200 uT (or jump delta >= 100 uT)
  -> NOOBIA P1 magnet wand mag=... | A magnet is hovering near me!
- Heading quadrant change: heading crosses N/E/S/W boundary and holds
  -> NOOBIA P1 compass heading to=North|East|South|West deg=... | Compass heading is ...
- Periodic sample:
  -> NOOBIA P0 compass status.sample heading=... mag=...
"""

from __future__ import annotations

import argparse
import json
import math
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

SAMPLE_INTERVAL = 30
EARTH_FIELD_MAX_UT = 120  # Earth's ambient magnetic field is ~25 to 65 uT. Anything >= 180 uT is a local magnet.
WAND_THRESHOLD_UT = 180


def read_hardware_mag() -> dict:
    """Invoke the magnetometer reader tool and return the sample dict."""
    cmd = os.environ.get("LYNX_MAGNET_BIN", "/usr/local/bin/lynx-magnetometer-read")
    if not os.path.exists(cmd):
        raise RuntimeError(f"Magnetometer read tool not found at {cmd}")

    res = subprocess.run([cmd], input="{}", capture_output=True, text=True, timeout=5)
    if res.returncode != 0:
        raise RuntimeError(f"Magnetometer read failed: {res.stderr.strip() or res.stdout.strip()}")

    data = json.loads(res.stdout)
    if "error" in data:
        raise RuntimeError(data["error"])
    return data


def calculate_heading_and_magnitude(raw_xyz: list[int | float]) -> tuple[float, float, str]:
    """Calculate total flux magnitude (uT) and 2D compass heading (0-360 deg, quadrant)."""
    x, y, z = raw_xyz[0], raw_xyz[1], raw_xyz[2]
    # In AK09918 gain is 1000 => raw / 10 is approx uT (or raw units)
    magnitude = math.sqrt(x * x + y * y + z * z) / 10.0

    # 2D azimuth in degrees (0 = North, 90 = East, 180 = South, 270 = West)
    rad = math.atan2(y, x)
    deg = (math.degrees(rad) + 360) % 360

    if 315 <= deg or deg < 45:
        cardinal = "North"
    elif 45 <= deg < 135:
        cardinal = "East"
    elif 135 <= deg < 225:
        cardinal = "South"
    else:
        cardinal = "West"

    return round(magnitude, 1), round(deg, 1), cardinal


def run(dry_run: bool = False, state_file: str | None = None,
        read_mag=read_hardware_mag,
        now: int | None = None) -> tuple[dict, int]:
    """One magnetometer sample. Returns (result_dict, exit_code)."""
    t = int(now if now is not None else now_ts())
    try:
        sense = import_sense()
    except SenseUnavailable as exc:
        return failure("magnet", exc)

    try:
        sample = read_mag()
        raw = sample.get("raw", [0, 0, 0])
        mag_ut, heading_deg, cardinal = calculate_heading_and_magnitude(raw)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        return failure("magnet", exc)

    path = state_path("magnet", state_file)
    state = load_state(path)

    sample_count = int(state.get("sample_count", 0)) + 1
    state["sample_count"] = sample_count

    emitted: list[str] = []
    prev_cardinal = state.get("cardinal")
    prev_wand = state.get("wand_active", False)

    wand_now = mag_ut >= WAND_THRESHOLD_UT

    # Event 1: Magnetic wand / magnet hover detection
    if wand_now and not prev_wand:
        line = emit_line(
            sense, 1, "magnet", "wand",
            fields={"mag_ut": mag_ut},
            text=f"A magnet is hovering near me ({mag_ut} uT)",
            dry_run=dry_run,
        )
        emitted.append(line)
        state["wand_active"] = True
    elif not wand_now and prev_wand:
        state["wand_active"] = False

    # Event 2: Cardinal compass heading transition
    if prev_cardinal is None:
        state["cardinal"] = cardinal
        state["heading_deg"] = heading_deg
    elif prev_cardinal != cardinal and not wand_now:
        line = emit_line(
            sense, 1, "compass", "heading",
            fields={"to": cardinal, "from": prev_cardinal, "deg": heading_deg},
            text=f"Compass heading turned to {cardinal} ({heading_deg}°)",
            dry_run=dry_run,
        )
        emitted.append(line)
        state["cardinal"] = cardinal
        state["heading_deg"] = heading_deg
    elif sample_count % SAMPLE_INTERVAL == 0:
        line = emit_line(
            sense, 0, "compass", "status.sample",
            fields={"cardinal": cardinal, "deg": heading_deg, "mag_ut": mag_ut},
            text=f"heading {cardinal} ({heading_deg}°), flux {mag_ut} uT",
            dry_run=dry_run,
        )
        emitted.append(line)

    if not dry_run:
        save_state(path, state)

    return (base_result("magnet", sampled={"mag_ut": mag_ut, "heading_deg": heading_deg, "cardinal": cardinal},
                        emitted=emitted, state=state), 0)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="print would-be sense lines; never write state or syslog")
    parser.add_argument("--state-file", default=None,
                        help="state file override")
    args = parser.parse_args(argv)
    try:
        result, code = run(dry_run=args.dry_run, state_file=args.state_file)
    except (OSError, RuntimeError, ValueError) as exc:
        result, code = failure("magnet", exc)
    return finish(result, code)


if __name__ == "__main__":
    sys.exit(main())
