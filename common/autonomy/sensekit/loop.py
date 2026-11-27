"""Generic multi-sense loop scheduler (NA-83)."""
from __future__ import annotations

import signal
import sys
import time
from typing import Callable, Dict, Optional

_stop = False


def _on_term(signum, frame):
    global _stop
    _stop = True


class SenseScheduler:
    """Schedules sense execution according to interval mappings."""

    def __init__(self):
        self.senses: Dict[str, Dict] = {}

    def register(self, name: str, run_fn: Callable[..., Any], interval_s: float):
        self.senses[name] = {
            "run": run_fn,
            "interval_s": interval_s,
            "last_run": 0.0,
        }

    def step(self, now: Optional[float] = None) -> Dict[str, Any]:
        now = now if now is not None else time.time()
        results = {}
        for name, item in self.senses.items():
            if now - item["last_run"] >= item["interval_s"]:
                try:
                    res = item["run"]()
                    results[name] = res
                except Exception as exc:
                    results[name] = {"ok": False, "error": str(exc)}
                item["last_run"] = now
        return results

    def run_forever(self, poll_interval_s: float = 0.5):
        global _stop
        signal.signal(signal.SIGTERM, _on_term)
        signal.signal(signal.SIGINT, _on_term)
        while not _stop:
            self.step()
            time.sleep(poll_interval_s)
