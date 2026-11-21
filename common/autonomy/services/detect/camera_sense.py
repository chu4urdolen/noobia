"""Camera sense emitter for Lynx (S1).

Reads camera frame, queries Nexus detect service (via E5 route),
and emits P1 on a NEW label, or P0/silent on repeated labels.
Strictly zero frame persistence.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import time
from urllib.request import Request, urlopen

# Import sense formatting
HERE = Path(__file__).resolve().parent
AUTONOMY = HERE.parents[1]
if str(AUTONOMY) not in sys.path:
    sys.path.insert(0, str(AUTONOMY))

from sense import format_line, emit


class CameraSense:
    def __init__(
        self,
        detect_url: str = "http://192.168.100.106:5050/detect",
        seen_window_s: float = 300.0,
        timeout_s: float = 5.0,
        emit_fn=None,
    ):
        # emit_fn(p, sense, event, fields=..., text=...) -> line. Defaults to
        # sense.emit (real syslog). Tests must pass a collector so they never
        # write sense lines into a live noobia-sense view.
        self.emit_fn = emit_fn or emit
        self.detect_url = detect_url
        self.seen_window_s = seen_window_s
        self.timeout_s = timeout_s
        self._last_seen: dict[str, float] = {}

    def process_frame(self, frame_bytes: bytes, now: float | None = None) -> list[str]:
        """Detect objects and emit sense lines for newly observed labels."""
        if now is None:
            now = time.time()

        req = Request(self.detect_url, data=frame_bytes, headers={"Content-Type": "image/jpeg"}, method="POST")
        try:
            with urlopen(req, timeout=self.timeout_s) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:
            return []

        objects = data.get("objects", [])
        emitted_lines = []

        for obj in objects:
            label = obj.get("label", "unknown")
            conf = float(obj.get("confidence", 0.0))
            last_time = self._last_seen.get(label)

            # P1 on a NEW label (never seen or not seen in seen_window_s)
            is_new = (last_time is None) or (now - last_time >= self.seen_window_s)
            p = 1 if is_new else 0

            self._last_seen[label] = now
            conf_str = f"{conf:.2f}"
            line = self.emit_fn(p, "camera", "object.seen", fields={"label": label, "conf": conf_str}, text=f"{label} seen by camera")
            emitted_lines.append(line)

        return emitted_lines
