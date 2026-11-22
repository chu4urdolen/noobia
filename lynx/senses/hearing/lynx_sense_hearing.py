#!/usr/bin/env python3
"""S9 hearing sense for Lynx: acoustic level sampling.

Sampled sense. Data source: ``/usr/local/share/lynx/agent-tools/lynx_microphone_level.sh``
or ``/usr/local/bin/lynx-mic-level``.
Expects JSON stdin ({}) and returns:
{"captured": true, "late_rms": float, "late_peak": int, ...}

Events:
- peak >= 100 or rms >= 30.0 -> NOOBIA P3 hearing sound.heard peak=... rms=...
- every 15 samples: NOOBIA P0 hearing status.sample peak=... rms=...
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

DEFAULT_MIC_BIN = "/usr/local/share/lynx/agent-tools/lynx_microphone_level.sh"
DEFAULT_ENABLED_FILE = "/var/lib/noobia/senses/hearing/enabled"
NEXUS_HEARING_URL = "http://192.168.100.106:112/api/v1/hearing"
HEARING_PEAK_THRESHOLD = 80
HEARING_RMS_THRESHOLD = 25.0
HEARING_SAMPLE_EVERY = 15


def is_hearing_enabled(enabled_file: str | Path = DEFAULT_ENABLED_FILE,
                       nexus_url: str = NEXUS_HEARING_URL) -> bool:
    # 1. Local file override if present
    p = Path(enabled_file)
    if p.exists():
        try:
            val = p.read_text().strip().lower()
            return val in ("1", "true", "on", "yes")
        except OSError:
            pass

    # 2. Check Nexus toggle over LAN
    try:
        import urllib.request
        req = urllib.request.Request(nexus_url, headers={"User-Agent": "LynxSense/1.0"})
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                return bool(data.get("enabled", False))
    except Exception:
        pass

    # 3. Disabled by default
    return False


def read_microphone_level(bin_path: str = DEFAULT_MIC_BIN) -> dict:
    cmd = os.environ.get("LYNX_MIC_BIN", bin_path)
    res = subprocess.run([cmd], input=b"{}\n", capture_output=True, timeout=8, check=True)
    return json.loads(res.stdout)


def run(dry_run: bool = False, state_file: str | None = None,
        reader=None, now: int | None = None,
        enabled: bool | None = None) -> tuple[dict, int]:
    t = int(now if now is not None else now_ts())
    # Disabled by default
    is_on = is_hearing_enabled() if enabled is None else enabled
    if not is_on:
        return base_result("hearing", enabled=False, emitted=[], dry_run=dry_run), 0

    try:
        sense = import_sense()
    except SenseUnavailable as exc:
        return failure("hearing", exc)

    try:
        data = (reader or read_microphone_level)()
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return failure("hearing", exc)

    if not data.get("captured"):
        return failure("hearing", RuntimeError(data.get("error", "capture failed")))

    peak = int(data.get("late_peak", 0))
    rms = float(data.get("late_rms", 0.0))

    path = state_path("hearing", state_file)
    state = load_state(path)
    emitted: list[str] = []
    samples = int(state.get("samples", 0)) + 1
    prev_heard = state.get("sound_heard", False)

    sound_heard = peak >= HEARING_PEAK_THRESHOLD or rms >= HEARING_RMS_THRESHOLD

    if samples == 1:
        # First sample sets baseline
        pass
    elif sound_heard and not prev_heard:
        line = emit_line(
            sense,
            1,
            "hearing",
            "sound.heard",
            fields={"peak": peak, "rms": round(rms, 1)},
            text=f"Lynx heard sound (peak={peak}, rms={round(rms, 1)})",
            dry_run=dry_run,
        )
        emitted.append(line)

    if samples % HEARING_SAMPLE_EVERY == 0:
        line = emit_line(
            sense,
            0,
            "hearing",
            "status.sample",
            fields={"peak": peak, "rms": round(rms, 1)},
            text=f"Hearing sample peak={peak} rms={round(rms, 1)}",
            dry_run=dry_run,
        )
        emitted.append(line)

    new_state = {
        "samples": samples,
        "sound_heard": sound_heard,
        "last_peak": peak,
        "last_rms": rms,
        "last_ts": t,
    }
    if not dry_run:
        save_state(path, new_state)

    result = base_result("hearing", emitted=emitted, dry_run=dry_run)
    result.update({
        "peak": peak,
        "rms": round(rms, 1),
        "sound_heard": sound_heard,
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
