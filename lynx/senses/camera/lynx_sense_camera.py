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
MACRO_EVERY = 5      # one macro (close-up) look per five
REAR = ("wide", "back")   # rear eyes; "back" is the macro
FRONT_WITH_EVERY_LOOK = True   # front camera picture after each rear one
SCENE_EVERY_S = 300  # a caption-only scene is spoken at most every 5 minutes


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
        state = {"boot": boot, "last_seen": {}, "failures": 0, "off": False, "turn": 0,
                 "dropped": [], "cam_failures": {}}
    emitted: list[str] = []

    if state.get("off"):
        return (base_result("camera", available=False, emitted=[],
                            detail="camera sense paused for this boot after repeated failures"), 0)

    # Rear eye: wide (IMX355) is her main eye; the macro (GC02M1) only focuses a
    # few cm away, so it looks every MACRO_EVERY-th turn (Tom, 2026-11-23).
    # Front (S5K3P9SP, Tom 2026-11-24): a picture with every look, right after
    # the rear one, so she sees both sides each minute. A camera that keeps
    # failing is dropped for the boot; the others go on.
    dropped = state.get("dropped", [])
    rear = [c for c in REAR if c in frame.CAMERAS and c not in dropped]
    turn = int(state.get("turn", 0))
    state["turn"] = turn + 1
    plan = []
    if rear:
        plan.append(rear[0] if len(rear) == 1 else
                    ("back" if turn % MACRO_EVERY == MACRO_EVERY - 1 else "wide"))
    if FRONT_WITH_EVERY_LOOK and "front" in frame.CAMERAS and "front" not in dropped:
        plan.append("front")
    if not plan:                       # everything dropped: try again from the start
        plan = [c for c in REAR if c in frame.CAMERAS][:1]
    results, sampled, details = [], {}, []
    for camera in plan:
        res, stop = _look_once(camera, state, sense, t, dry_run, look, len(plan) + len(rear))
        results.append(res)
        emitted += res.get("emitted", [])
        if res.get("sampled"):
            sampled[camera] = res["sampled"]
        if res.get("detail"):
            details.append(res["detail"])
        if stop:
            break
    if not dry_run:
        save_state(path, state)
    ok_any = any(r.get("sampled") for r in results)
    out = base_result("camera", available=ok_any or not details, emitted=emitted,
                      **({"detail": "; ".join(details)} if details else {}))
    if sampled:
        first = next(iter(sampled.values()))
        out["sampled"] = dict(first, cameras=sampled)
    if state.get("failures"):
        out["failures"] = state["failures"]
    if state.get("off"):
        out["available"] = False
    return out, 0


def _look_once(camera, state, sense, t, dry_run, look, n_cams):
    """One camera's look. Returns (partial result, stop_the_rest)."""
    emitted: list[str] = []
    result = (look or frame.look)(wait_s=0.0, camera=camera)
    if not result.get("ok"):
        if result.get("busy"):                        # Lynx is using it herself
            return {"detail": "camera busy"}, True
        if frame.disabled():
            return {"detail": result.get("error")}, True
        if "not prepared" in str(result.get("error", "")):
            # A known state, not a malfunction: the stack is prepared per boot
            # (lynx-camera-keeper on Nexus). Wait quietly; no failure count.
            return {"detail": result.get("error")}, True
        fails = state.setdefault("cam_failures", {})
        fails[camera] = int(fails.get(camera, 0)) + 1
        state["failures"] = fails[camera]
        detail = f"{camera}: {result.get('error', 'unknown')}"
        if fails[camera] >= MAX_FAILURES and n_cams > 1:
            state.setdefault("dropped", []).append(camera)
            emitted.append(emit_line(sense, 3, "camera", "unavailable",
                                     fields={"cam": camera, "failures": fails[camera]},
                                     text=f"{camera} camera paused for this boot: {detail}"[:200],
                                     dry_run=dry_run))
        elif fails[camera] >= MAX_FAILURES:
            state["off"] = True
            emitted.append(emit_line(sense, 3, "camera", "unavailable",
                                     fields={"failures": state["failures"]},
                                     text=f"camera paused for this boot: {detail}"[:200],
                                     dry_run=dry_run))
        return {"detail": detail, "emitted": emitted}, False

    state["failures"] = 0
    state.setdefault("cam_failures", {})[camera] = 0
    last_seen: dict[str, float] = state.get("last_seen", {})
    cam = result.get("camera", camera)
    # Only labels with a real score (YOLO) count as seen; Florence-2's
    # unscored guesses (confidence exactly 0.5) live in its caption instead.
    objects = [o for o in result["objects"] if abs(float(o.get("confidence", 0)) - 0.5) > 1e-6]
    labels = [frame.clean_label(o.get("label")) for o in objects]
    caption = str(result.get("caption", ""))
    if not objects and caption:
        # No confirmed (scored) object, but Florence-2 described the scene -
        # what she has at night. Spoken at most once per SCENE_EVERY_S per camera.
        key = f"last_scene_t_{cam}"
        speak = t - float(state.get(key, state.get("last_scene_t", -1e12) if cam != "front" else -1e12)) >= SCENE_EVERY_S
        if speak:
            state[key] = t
            state["last_scene_t"] = t
        emitted.append(emit_line(sense, 1 if speak else 0, "camera", "scene.seen",
                                 fields={"cam": cam}, text=caption, dry_run=dry_run))
    elif not objects:
        emitted.append(emit_line(sense, 0, "camera", "frame.analyzed",
                                 fields={"objects": 0, "cam": cam},
                                 text="frame analyzed, no objects recognized", dry_run=dry_run))
    else:
        new = [lb for lb in labels if t - float(last_seen.get(f"{cam}:{lb}", -1e12)) >= SEEN_WINDOW_S]
        for lb in labels:
            last_seen[f"{cam}:{lb}"] = t
        text = frame.items_text(objects) + (f" ~ {caption}" if caption else "")
        emitted.append(emit_line(sense, 1 if new else 0, "camera", "objects.seen",
                                 fields={"cam": cam, "n": len(objects)},
                                 text=text, dry_run=dry_run))
    # Forget labels not seen for an hour, so state stays small.
    state["last_seen"] = {k: v for k, v in last_seen.items() if t - float(v) < 3600}
    return {"emitted": emitted, "sampled": {"objects_count": len(objects), "labels": labels,
                                            "elapsed_s": result.get("elapsed_s")}}, False


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
