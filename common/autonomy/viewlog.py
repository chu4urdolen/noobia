"""One write point for Noobia's syslog views (noobia-sense, -autonomy, -aigel, -agent).

Safety rule (Gwyn, 2026-11-21): a test must never write into a live view. Test
runs on Nexus had put ~200 lines into the real journal in one day, including
"Lynx battery is critical" and "Wi-Fi went down". With autonomy running, Aigel
would have read them as real perceptions and messaged Lynx.

``NOOBIA_VIEWS_SINK`` decides where lines go:
- ``syslog``: always write to syslog;
- ``null``: never write; lines are kept in ``CAPTURED``, the last 1000;
- unset: ``syslog``, **unless** the process is running unit tests
  (``unittest`` imported), in which case ``null``.

Production code never imports ``unittest``, which is checked by
test_viewlog.py.
"""

from __future__ import annotations

import collections
import os
import sys
import syslog

CAPTURED: collections.deque = collections.deque(maxlen=1000)


def sink() -> str:
    value = os.environ.get("NOOBIA_VIEWS_SINK", "").strip().lower()
    if value in ("syslog", "null"):
        return value
    return "null" if "unittest" in sys.modules else "syslog"


def write(ident: str, line: str, *, level: int = syslog.LOG_NOTICE,
          option: int = syslog.LOG_PID) -> bool:
    """Write one line to a view. Returns True if it went to syslog."""
    if sink() == "null":
        CAPTURED.append((ident, line))
        return False
    syslog.openlog(ident, option, syslog.LOG_USER)
    try:
        syslog.syslog(level, line)
    finally:
        syslog.closelog()
    return True
