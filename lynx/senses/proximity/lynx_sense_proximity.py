#!/usr/bin/env python3
"""S6 proximity sense for Lynx: infrared proximity sensor (TCS3701).

Sampled sense. Data source: ``/usr/local/bin/lynx-proximity-read`` (or $LYNX_PROXIMITY_BIN).
Expects JSON stdin ({}) and returns:
{"sensor":"tcs3701 ps","raw":[detection_flag, distance_raw, gain], ...}
Distance: 1023 is clear/far, lower values (e.g. <= 800) indicate an object near.

Events:
- distance <= 800 -> NOOBIA P3 proximity near dist=...
- distance > 900 -> NOOBIA P3 proximity far dist=...
- every 15 samples: NOOBIA P0 proximity status.sample dist=...
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

DEFAULT_PROXIMITY_BIN = "/usr/local/bin/lynx-proximity-read"
PROXIMITY_NEAR_THRESHOLD = 800
PROXIMITY_FAR_THRESHOLD = 900
PROXIMITY_SAMPLE_EVERY = 15


def read_proximity_sensor(bin_path: str = DEFAULT_PROXIMITY_BIN) -> dict:
    cmd = os.environ.get("LYNX_PROXIMITY_BIN", bin_path)
    res = subprocess.run([cmd], input=b"{}\n", capture_output=True, timeout=5, check=True)
    return json.loads(res.stdout)


def run(dry_run: bool = False, state_file: str | None = None,
        reader=None, now: int | None = None) -> tuple[dict, int]:
    t = int(now if now is not None else now_ts())
    try:
        sense = import_sense()
    except SenseUnavailable as exc:
        return failure("proximity", exc)

    try:
        data = (reader or read_proximity_sensor)()
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return failure("proximity", exc)

    raw_list = data.get("raw") or []
    if len(raw_list) < 2:
        return failure("proximity", ValueError("malformed raw proximity sensor data"))
    dist_val = int(raw_list[1])

    path = state_path("proximity", state_file)
    state = load_state(path)
    emitted: list[str] = []
    samples = int(state.get("samples", 0)) + 1
    prev_state = state.get("state")

    current_state = "near" if dist_val <= PROXIMITY_NEAR_THRESHOLD else ("far" if dist_val >= PROXIMITY_FAR_THRESHOLD else prev_state or "far")

    if prev_state is None:
        # First sample sets baseline
        pass
    elif current_state != prev_state:
        line = emit_line(
            sense,
            3,
            "proximity",
            current_state,
            fields={"dist": dist_val},
            text=f"Lynx proximity sensor detected {current_state} (dist={dist_val})",
            dry_run=dry_run,
        )
        emitted.append(line)

    if samples % PROXIMITY_SAMPLE_EVERY == 0:
        line = emit_line(
            sense,
            0,
            "proximity",
            "status.sample",
            fields={"dist": dist_val, "state": current_state},
            text=f"Proximity sample dist={dist_val}",
            dry_run=dry_run,
        )
        emitted.append(line)

    new_state = {
        "samples": samples,
        "state": current_state,
        "last_dist": dist_val,
        "last_ts": t,
    }
    if not dry_run:
        save_state(path, new_state)

    result = base_result("proximity", emitted=emitted, dry_run=dry_run)
    result.update({
        "dist": dist_val,
        "state": current_state,
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
