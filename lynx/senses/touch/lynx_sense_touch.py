#!/usr/bin/env python3
"""S2 touch sense for Lynx (PLAN.md): tap/hold events from TOUCH_STATUS.

Event sense, P5 (routine change). Reads the runtime's touch queue state
with the non-consuming TOUCH_STATUS call only (never TOUCH_POLL, which
is the sole popper of the shared 8-slot queue - see
lynx/linux-port/docs/LYNX-TOUCH-EVENTS-DESIGN-20261121.md), and emits
on the finger down/up transition:

- press <= 800 ms  ->  NOOBIA P5 touch tap dur_ms=... queued=... dropped=...
- press >  800 ms  ->  NOOBIA P5 touch hold dur_ms=... queued=... dropped=...

Convention (Aigel-style defaults, configurable, honest):
- The press is measured from the first sample that sees ``down=1`` to
  the first sample that sees ``down=0``; it is therefore quantized to
  the poll interval (the service loop polls every 2 s).
- The very first sample after a boot (or after any state loss) only sets
  the baseline and never emits: a finger that is already down when the
  sense starts has an unknown start time.
- ``queued``/``dropped`` are reported on the emitted line for context;
  they are never consumed.
- A program (VM) can also generate touch records, so the line carries no
  ``cause`` field; Aigel decides what to make of it.

Bounded one-shot; JSON on stdout; --dry-run prints the would-be line and
never touches syslog. The canonical formatter comes from the installed
autonomy dir (never duplicated).

    python3 /usr/local/lib/noobia/senses/touch/lynx_sense_touch.py [--dry-run]
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Import the shared sense library (installed alongside: ../common/, or
# found next to this file in the repository layout).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from lynx_senses_lib import (  # noqa: E402
    TOUCH_HOLD_MS,
    SenseUnavailable,
    base_result,
    emit_line,
    failure,
    finish,
    import_sense,
    load_state,
    now_ts,
    nrp_touch_status,
    save_state,
    state_path,
)


def read_boot_id() -> str:
    """Lynx boot id (env LYNX_BOOT_ID is a test override)."""
    env = os.environ.get("LYNX_BOOT_ID")
    if env:
        return env
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except OSError:
        return ""


def run(dry_run: bool = False, state_file: str | None = None,
        hold_ms: int = TOUCH_HOLD_MS,
        read_touch=nrp_touch_status,
        boot_id: str = "",
        now: int | None = None) -> tuple[dict, int]:
    """One touch sample. Returns (result_dict, exit_code)."""
    t = int(now if now is not None else now_ts())
    try:
        sense = import_sense()
    except SenseUnavailable as exc:
        return failure("touch", exc)

    try:
        sampled = read_touch()
    except (OSError, ValueError, RuntimeError) as exc:
        return failure("touch", exc)

    path = state_path("touch", state_file)
    state = load_state(path)

    if not boot_id:
        boot_id = read_boot_id()

    emitted: list[str] = []
    if state.get("boot_id") not in (None, boot_id):
        # New boot (or state from a different boot): re-baseline quietly.
        state = {"boot_id": boot_id, "down": bool(sampled["finger_down"]),
                 "down_since": None, "dropped": int(sampled["dropped"]),
                 "queued": int(sampled["queued"]),
                 "last_event": None}
    else:
        state.setdefault("boot_id", boot_id)
        was_down = bool(state.get("down"))
        down_now = bool(sampled["finger_down"])
        if not was_down and down_now:
            state["down_since"] = t
        elif was_down and not down_now:
            since = state.get("down_since")
            if since is not None:
                dur_ms = max(0, (t - int(since)) * 1000)
                event = "tap" if dur_ms <= hold_ms else "hold"
                last_emitted = state.get("last_emitted_ts", 0)
                if t - last_emitted >= 5:
                    line = emit_line(
                        sense, 5, "touch", event,
                        fields={"dur_ms": dur_ms,
                                "queued": sampled["queued"],
                                "dropped": sampled["dropped"]},
                        text=("a tap on the panel" if event == "tap"
                              else "a long hold on the panel"),
                        dry_run=dry_run)
                    emitted.append(line)
                    state["last_event"] = event
                    state["last_emitted_ts"] = t
            state["down_since"] = None
        state["down"] = down_now
        state["queued"] = int(sampled["queued"])
        state["dropped"] = int(sampled["dropped"])

    if not dry_run:
        save_state(path, state)
    return (base_result("touch", sampled=sampled, emitted=emitted,
                        state=state), 0)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true",
                        help="print would-be sense lines; never write state or syslog")
    parser.add_argument("--state-file", default=None,
                        help="state file (default: /var/lib/noobia/senses/touch/state.json)")
    args = parser.parse_args(argv)
    try:
        result, code = run(dry_run=args.dry_run, state_file=args.state_file)
    except (OSError, RuntimeError, ValueError) as exc:
        result, code = failure("touch", exc)
    return finish(result, code)


if __name__ == "__main__":
    sys.exit(main())
