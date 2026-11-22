#!/usr/bin/env python3
"""S5 light sense for Lynx: ambient light sensor (TCS3408).

Sampled sense. Data source: ``/usr/local/bin/lynx-light-read`` (or $LYNX_LIGHT_BIN).
Expects JSON stdin ({}) and returns:
{"sensor":"tcs3408 als","raw":[raw_als, ...],"gain":1,...}

Events:
- raw[0] <= 2 (dark/covered) -> NOOBIA P3 light dark raw=...
- raw[0] >= 5 (bright/room light) -> NOOBIA P3 light bright raw=...
- every 15 samples: NOOBIA P0 light status.sample raw=...
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

DEFAULT_LIGHT_BIN = "/usr/local/bin/lynx-light-read"
LIGHT_DARK_THRESHOLD = 2
LIGHT_BRIGHT_THRESHOLD = 5
LIGHT_SAMPLE_EVERY = 15


def read_light_sensor(bin_path: str = DEFAULT_LIGHT_BIN) -> dict:
    cmd = os.environ.get("LYNX_LIGHT_BIN", bin_path)
    res = subprocess.run([cmd], input=b"{}\n", capture_output=True, timeout=5, check=True)
    return json.loads(res.stdout)


def run(dry_run: bool = False, state_file: str | None = None,
        reader=None, now: int | None = None) -> tuple[dict, int]:
    t = int(now if now is not None else now_ts())
    try:
        sense = import_sense()
    except SenseUnavailable as exc:
        return failure("light", exc)

    try:
        data = (reader or read_light_sensor)()
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return failure("light", exc)

    raw_list = data.get("raw") or []
    if not raw_list:
        return failure("light", ValueError("empty raw light sensor data"))
    raw_val = int(raw_list[0])

    path = state_path("light", state_file)
    state = load_state(path)
    emitted: list[str] = []
    samples = int(state.get("samples", 0)) + 1
    prev_mode = state.get("mode")

    current_mode = "dark" if raw_val <= LIGHT_DARK_THRESHOLD else ("bright" if raw_val >= LIGHT_BRIGHT_THRESHOLD else prev_mode or "ambient")

    if prev_mode is None:
        # First sample sets baseline
        pass
    elif current_mode != prev_mode and current_mode in ("dark", "bright"):
        line = emit_line(
            sense,
            1,
            "light",
            current_mode,
            fields={"raw": raw_val},
            text=f"Lynx light sensor detected {current_mode} (raw={raw_val})",
            dry_run=dry_run,
        )
        emitted.append(line)

    if samples % LIGHT_SAMPLE_EVERY == 0:
        line = emit_line(
            sense,
            0,
            "light",
            "status.sample",
            fields={"raw": raw_val, "mode": current_mode},
            text=f"Light sample raw={raw_val}",
            dry_run=dry_run,
        )
        emitted.append(line)

    new_state = {
        "samples": samples,
        "mode": current_mode,
        "last_raw": raw_val,
        "last_ts": t,
    }
    if not dry_run:
        save_state(path, new_state)

    result = base_result("light", emitted=emitted, dry_run=dry_run)
    result.update({
        "raw": raw_val,
        "mode": current_mode,
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
