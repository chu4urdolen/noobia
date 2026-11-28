#!/usr/bin/env python3
"""lynx_camera_photo: Lynx consciously takes one picture and learns what she sees.

Her own tool (Tom, 2026-11-22). It shares the camera lock with the camera
sense (waits up to 10 s if the sense is mid-capture), uses the same proven
capture and Nexus detection (lynx_camera_frame.look), and:

- returns {"ok", "you_see": "laptop, cat", "objects": [...]} to her as the
  tool result;
- also writes the look into her sense log, as Tom asked, so it is part of
  her inputs - marked cause=self, so it is context only and can never
  trigger a new reaction (no see -> react -> photo -> see loop).

Reads JSON arguments on stdin ({} - no arguments). Prints one JSON object.
"""
import json
import os
from pathlib import Path
import sys

SENSES = Path(os.environ.get("LYNX_SENSES_ROOT", "/usr/local/lib/noobia/senses"))
sys.path.insert(0, str(SENSES / "camera"))
sys.path.insert(0, str(SENSES / "common"))
import lynx_camera_frame as frame  # noqa: E402


def log_self_look(result) -> str | None:
    """One cause=self line in noobia-sense; never fatal."""
    try:
        from lynx_senses_lib import emit_line, import_sense
        sense = import_sense()
        if result["objects"]:
            return emit_line(sense, 0, "camera", "objects.seen",
                             fields={"cam": result["camera"], "n": len(result["objects"]), "cause": "self"},
                             text=result["items"])
        return emit_line(sense, 0, "camera", "frame.analyzed",
                         fields={"objects": 0, "cam": result["camera"], "cause": "self"},
                         text="my own photo, no objects recognized")
    except Exception:
        return None


def main() -> int:
    try:
        args = json.loads(sys.stdin.read(4096) or "{}")
    except (OSError, ValueError):
        args = {}
    camera = args.get("camera", "both") if isinstance(args, dict) else "both"
    if camera not in ("both", "dual", "all") and camera not in frame.CAMERAS:
        print(json.dumps({"ok": False, "error": f"unknown camera {camera!r}; use front, back, wide, or both"}))
        return 1

    is_async = bool(args.get("async", False))
    if is_async:
        try:
            sys.path.insert(0, "/usr/local/lib/noobia/autonomy")
            sys.path.insert(0, str(Path(os.environ.get("NOOBIA", "/noobia")) / "common" / "autonomy"))
            import uuid
            from asyncjob import AsyncJobManager
            cap_id = f"cap-{uuid.uuid4().hex[:8]}"

            def _async_look():
                if camera in ("both", "dual", "all"):
                    res_front = frame.look(wait_s=10.0, camera="front")
                    res_rear = frame.look(wait_s=10.0, camera="wide" if "wide" in frame.CAMERAS else "back")
                    parts = []
                    if res_front.get("ok"):
                        log_self_look(res_front)
                        f_labels = [o["label"].replace("_", " ") for o in res_front.get("objects", [])]
                        f_clean = ", ".join(dict.fromkeys(frame.clean_label(l).replace("_", " ") for l in f_labels))
                        if f_clean:
                            parts.append(f"in front: {f_clean}")
                    if res_rear.get("ok"):
                        log_self_look(res_rear)
                        r_labels = [o["label"].replace("_", " ") for o in res_rear.get("objects", [])]
                        r_clean = ", ".join(dict.fromkeys(frame.clean_label(l).replace("_", " ") for l in r_labels))
                        if r_clean:
                            parts.append(f"in back: {r_clean}")
                    summary = "; ".join(parts) or "nothing recognized"
                    return f"camera objects.seen capture={cap_id} cam=both | {summary}"
                res = frame.look(wait_s=10.0, camera=camera)
                if not res.get("ok"):
                    raise RuntimeError(res.get("error", "camera capture failed"))
                labels = [o["label"].replace("_", " ") for o in res["objects"]]
                clean = ", ".join(dict.fromkeys(frame.clean_label(l).replace("_", " ") for l in labels)) or "nothing recognized"
                log_self_look(res)
                return f"camera objects.seen capture={cap_id} cam={camera} n={len(res['objects'])} | {clean}"

            manager = AsyncJobManager()
            run_res = manager.run_async("camera", "look", _async_look, cause=cap_id, use_fork=True)
            if not run_res.get("ok"):
                print(json.dumps({"ok": False, "busy": True, "error": run_res.get("error")}))
                return 1
            print(json.dumps({
                "ok": True,
                "async": True,
                "capture_id": cap_id,
                "camera": camera,
                "job_id": run_res.get("job_id"),
                "sentence": f"Camera capture {cap_id} started in the background; objects will stream into your senses."
            }))
            return 0
        except Exception as exc:
            print(json.dumps({"ok": False, "error": f"async camera look failed: {exc}"}))
            return 1

    if camera in ("both", "dual", "all"):
        res_front = frame.look(wait_s=10.0, camera="front")
        res_rear = frame.look(wait_s=10.0, camera="wide" if "wide" in frame.CAMERAS else "back")
        if not res_front.get("ok") and not res_rear.get("ok"):
            err = res_front.get("error") or res_rear.get("error") or "camera unavailable"
            print(json.dumps({"ok": False, "error": err}))
            return 1

        all_objects = []
        descriptions = []
        logged = False
        if res_front.get("ok"):
            f_labels = [o["label"].replace("_", " ") for o in res_front.get("objects", [])]
            f_clean = ", ".join(dict.fromkeys(frame.clean_label(l).replace("_", " ") for l in f_labels))
            if f_clean:
                descriptions.append(f"In front: {f_clean}")
            for o in res_front.get("objects", []):
                all_objects.append({"camera": "front", "label": frame.clean_label(o["label"]), "confidence": round(float(o["confidence"]), 2)})
            if log_self_look(res_front) is not None:
                logged = True

        if res_rear.get("ok"):
            r_labels = [o["label"].replace("_", " ") for o in res_rear.get("objects", [])]
            r_clean = ", ".join(dict.fromkeys(frame.clean_label(l).replace("_", " ") for l in r_labels))
            if r_clean:
                descriptions.append(f"In back: {r_clean}")
            for o in res_rear.get("objects", []):
                all_objects.append({"camera": res_rear.get("camera", "rear"), "label": frame.clean_label(o["label"]), "confidence": round(float(o["confidence"]), 2)})
            if log_self_look(res_rear) is not None:
                logged = True

        you_see = "; ".join(descriptions) if descriptions else "nothing you recognize"
        out = {
            "ok": True,
            "camera": "both",
            "you_see": you_see,
            "objects": all_objects,
            "front": {"ok": res_front.get("ok", False), "objects": res_front.get("objects", [])},
            "rear": {"ok": res_rear.get("ok", False), "objects": res_rear.get("objects", [])},
            "logged": logged
        }
        print(json.dumps(out))
        return 0

    result = frame.look(wait_s=10.0, camera=camera)
    if not result.get("ok"):
        print(json.dumps({"ok": False, "error": result.get("error", "camera unavailable")}))
        return 1
    labels = [o["label"].replace("_", " ") for o in result["objects"]]
    out = {"ok": True, "camera": result["camera"],
           "you_see": ", ".join(dict.fromkeys(frame.clean_label(l).replace("_", " ") for l in labels)) or "nothing you recognize",
           "objects": [{"label": frame.clean_label(o["label"]), "confidence": round(float(o["confidence"]), 2)}
                       for o in result["objects"]],
           "elapsed_s": result.get("elapsed_s")}
    out["logged"] = log_self_look(result) is not None
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
