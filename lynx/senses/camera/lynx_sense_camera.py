#!/usr/bin/env python3
"""S1 camera sense for Lynx, v2 (Tom's design, Gwyn 2026-11-22).

Once a minute (the senses loop sets the cadence) Lynx takes one real look
with her rear camera and reports it as ONE line per frame:

    NOOBIA P1 camera objects.seen cam=back n=3 | laptop(0.75)/person(0.87)/cat(0.45)
    NOOBIA P0 camera objects.seen cam=back n=2 | laptop(0.74)/cat(0.51)     (nothing new)
    NOOBIA P0 camera frame.analyzed objects=0 cam=back | frame analyzed, no objects recognized

- P1 when any label is new (not seen in the last SEEN_WINDOW_S), else P0.
  The ranker turns the P1 line into "With your back camera you see laptop,
  person, cat." (pattern camera-objects).
- The look itself (lock, capture, Nexus detection) is lynx_camera_frame.look().
  If Lynx's own photo tool holds the camera, this minute is skipped quietly.
- Failures are honest and bounded: after MAX_FAILURES consecutive failed
  looks the sense stops trying for the rest of this boot and says so once
  (P3 camera.unavailable). A camera that crashes or hangs is never hammered.
- Disable: /etc/lynx/disable-camera-capture or /etc/noobia/camera.disable.

    python3 /usr/local/lib/noobia/senses/camera/lynx_sense_camera.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
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
import lynx_camera_frame as frame  # noqa: E402

SEEN_WINDOW_S = 300.0
MAX_FAILURES = 3


def boot_id() -> str:
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except OSError:
        return ""


def run(dry_run: bool = False, state_file: str | None = None, look=None,
        now: float | None = None, boot: str | None = None) -> tuple[dict, int]:
    t = float(now if now is not None else now_ts())
    try:
        sense = import_sense()
    except SenseUnavailable as exc:
        return failure("camera", exc)

    path = state_path("camera", state_file)
    state = load_state(path)
    boot = boot if boot is not None else boot_id()
    if state.get("boot") != boot:          # a new boot gets a fresh chance
        state = {"boot": boot, "last_seen": {}, "failures": 0, "off": False}
    emitted: list[str] = []

    if state.get("off"):
        return (base_result("camera", available=False, emitted=[],
                            detail="camera sense paused for this boot after repeated failures"), 0)

    result = (look or frame.look)(wait_s=0.0)
    if not result.get("ok"):
        if result.get("busy"):                        # Lynx is using it herself
            return (base_result("camera", available=True, emitted=[], detail="camera busy"), 0)
        if frame.disabled():
            return (base_result("camera", disabled=True, emitted=[], detail=result.get("error")), 0)
        if "not prepared" in str(result.get("error", "")):
            # A known state, not a malfunction: the stack is prepared per boot
            # (lynx-camera-keeper on Nexus). Wait quietly; no failure count.
            return (base_result("camera", available=False, emitted=[], detail=result.get("error")), 0)
        state["failures"] = int(state.get("failures", 0)) + 1
        detail = result.get("error", "unknown")
        if state["failures"] >= MAX_FAILURES:
            state["off"] = True
            emitted.append(emit_line(sense, 3, "camera", "unavailable",
                                     fields={"failures": state["failures"]},
                                     text=f"camera paused for this boot: {detail}"[:200],
                                     dry_run=dry_run))
        if not dry_run:
            save_state(path, state)
        return (base_result("camera", available=False, emitted=emitted, detail=detail,
                            failures=state["failures"]), 0)

    state["failures"] = 0
    last_seen: dict[str, float] = state.get("last_seen", {})
    objects, labels = result["objects"], result["labels"]
    if not objects:
        emitted.append(emit_line(sense, 0, "camera", "frame.analyzed",
                                 fields={"objects": 0, "cam": result.get("camera", "back")},
                                 text="frame analyzed, no objects recognized", dry_run=dry_run))
    else:
        new = [lb for lb in labels if t - float(last_seen.get(lb, -1e12)) >= SEEN_WINDOW_S]
        for lb in labels:
            last_seen[lb] = t
        emitted.append(emit_line(sense, 1 if new else 0, "camera", "objects.seen",
                                 fields={"cam": result.get("camera", "back"), "n": len(objects)},
                                 text=result["items"], dry_run=dry_run))
    # Forget labels not seen for an hour, so state stays small.
    state["last_seen"] = {k: v for k, v in last_seen.items() if t - float(v) < 3600}
    if not dry_run:
        save_state(path, state)
    return (base_result("camera", sampled={"objects_count": len(objects), "labels": labels,
                                           "elapsed_s": result.get("elapsed_s")},
                        emitted=emitted), 0)


def loop(every_s: float = 60.0) -> int:
    """Its own process (OpenRC lynx-camera-sense), so a 6 s look never blocks
    the touch, hearing or motion senses. Stops cleanly on SIGTERM."""
    import signal
    import time
    stop = []
    signal.signal(signal.SIGTERM, lambda *a: stop.append(1))
    nxt = time.monotonic()
    while not stop:
        if time.monotonic() >= nxt:
            try:
                result, _ = run()
                if not result.get("ok", True) or result.get("detail"):
                    print(json.dumps(result, sort_keys=True)[:300], file=sys.stderr, flush=True)
            except Exception as exc:   # one bad look never ends the sense
                print(f"camera look error: {type(exc).__name__}: {str(exc)[:160]}", file=sys.stderr, flush=True)
            nxt = time.monotonic() + every_s
        time.sleep(1.0)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true",
                        help="take one real look but print the would-be line; write nothing")
    parser.add_argument("--loop", action="store_true", help="look every --every seconds until SIGTERM")
    parser.add_argument("--every", type=float, default=60.0)
    parser.add_argument("--state-file", default=None)
    args = parser.parse_args(argv)
    if args.loop:
        return loop(max(10.0, args.every))
    try:
        result, code = run(dry_run=args.dry_run, state_file=args.state_file)
    except (OSError, LookupError, ValueError) as exc:
        result, code = failure("camera", exc)
    return finish(result, code)


if __name__ == "__main__":
    sys.exit(main())
