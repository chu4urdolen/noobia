#!/usr/bin/env python3
"""B1 alert slider sense for Lynx: tri-state magnetic key (top=silent, mid=vibrate, bot=ring).

Transition sense, P1. Reads the physical Alert Slider position on OnePlus Nord 3:
- silent:   top position (up-hall triggered)
- vibrate:  middle position (neither hall triggered)
- ring:     bottom position (down-hall triggered)

Events:
- position change: NOOBIA P1 body slider.change to=silent|vibrate|ring from=... | Alert slider moved to ...
- every 60 samples: NOOBIA P0 body status.sample slider=...

Data sources checked:
1. Sysfs attribute /sys/bus/i2c/devices/0-000d or /sys/bus/i2c/devices/0-000c
2. Hall effect sysfs state: /sys/class/hall/tri_state_key or /sys/devices/platform/tri_state_key/state
3. Mock / custom override via LYNX_SLIDER_FIXTURE or LYNX_SLIDER_STATE
"""

from __future__ import annotations

import argparse
import json
import os
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

SAMPLE_INTERVAL = 60


def read_hardware_slider() -> str:
    """Read the slider position from sysfs or fixtures.
    
    Returns 'silent', 'vibrate', 'ring', or raises RuntimeError/OSError.
    """
    override = os.environ.get("LYNX_SLIDER_STATE")
    if override in ("silent", "vibrate", "ring"):
        return override

    fixture_path = os.environ.get("LYNX_SLIDER_FIXTURE")
    if fixture_path and os.path.exists(fixture_path):
        data = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
        rt = data.get("runtime", {})
        up = rt.get("uphall_triggered", False)
        down = rt.get("downhall_triggered", False)
        if up and not down:
            return "silent"
        elif down and not up:
            return "ring"
        else:
            return "vibrate"

    # Direct sysfs paths on OnePlus Nord 3
    sysfs_state = Path("/sys/devices/platform/tri_state_key/state")
    if sysfs_state.exists():
        raw = sysfs_state.read_text().strip().lower()
        if "1" in raw or "silent" in raw or "up" in raw:
            return "silent"
        elif "2" in raw or "vibrate" in raw or "mid" in raw:
            return "vibrate"
        elif "3" in raw or "ring" in raw or "down" in raw:
            return "ring"

    # Up-hall (0-000d) and Down-hall (0-000c) sysfs devices
    uphall = Path("/sys/bus/i2c/devices/0-000d")
    downhall = Path("/sys/bus/i2c/devices/0-000c")
    if uphall.exists() and downhall.exists():
        up_val = (uphall / "state").read_text().strip() if (uphall / "state").exists() else "0"
        down_val = (downhall / "state").read_text().strip() if (downhall / "state").exists() else "0"
        if up_val == "1":
            return "silent"
        elif down_val == "1":
            return "ring"
        else:
            return "vibrate"

    raise RuntimeError("Tri-state alert slider hardware not available")


def run(dry_run: bool = False, state_file: str | None = None,
        read_slider=read_hardware_slider,
        now: int | None = None) -> tuple[dict, int]:
    """One slider sample. Returns (result_dict, exit_code)."""
    t = int(now if now is not None else now_ts())
    try:
        sense = import_sense()
    except SenseUnavailable as exc:
        return failure("slider", exc)

    try:
        current_pos = read_slider()
    except (OSError, ValueError, RuntimeError) as exc:
        return failure("slider", exc)

    path = state_path("slider", state_file)
    state = load_state(path)

    sample_count = int(state.get("sample_count", 0)) + 1
    state["sample_count"] = sample_count

    emitted: list[str] = []
    prev_pos = state.get("position")

    if prev_pos is None:
        # First sample: set baseline quietly without noisy emission
        state["position"] = current_pos
        state["last_change_ts"] = t
    elif prev_pos != current_pos:
        # Transition event
        line = emit_line(
            sense, 1, "body", "slider.change",
            fields={"to": current_pos, "from": prev_pos},
            text=f"Alert slider moved to {current_pos}",
            dry_run=dry_run,
        )
        emitted.append(line)
        state["position"] = current_pos
        state["last_change_ts"] = t
    elif sample_count % SAMPLE_INTERVAL == 0:
        # Periodic sample
        line = emit_line(
            sense, 0, "body", "status.sample",
            fields={"slider": current_pos},
            text=f"alert slider at {current_pos}",
            dry_run=dry_run,
        )
        emitted.append(line)

    if not dry_run:
        save_state(path, state)

    return (base_result("slider", sampled={"position": current_pos},
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
        result, code = failure("slider", exc)
    return finish(result, code)


if __name__ == "__main__":
    sys.exit(main())
