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
        sys.stdin.read(4096)
    except OSError:
        pass
    result = frame.look(wait_s=10.0)
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
