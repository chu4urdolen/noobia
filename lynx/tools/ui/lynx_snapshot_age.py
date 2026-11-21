"""Snapshot freshness and boot identity for Lynx status snapshots.

A saved snapshot is history. This module tells a reader how old it is and
whether Lynx has rebooted, so an old capture can never pass for the current
state. It never changes validation: a stale ``validated`` is still only what
the phone said at capture time, and attended evidence stays historical.
"""

from datetime import datetime, timezone
import re

MAX_AGE_S = 15 * 60       # older than this: stale
CLOCK_SKEW_S = 2 * 60     # further in the future than this: clock problem
BOOT_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

STATES = ("fresh", "stale", "future", "unknown_time", "malformed_time")
BOOT_STATES = ("same_as_previous", "changed_since_previous", "no_previous", "unknown")


def boot_id(value):
    """A normalized boot ID, or None when absent or malformed."""
    if isinstance(value, dict):
        value = value.get("boot_id")
    if isinstance(value, str) and BOOT_ID.fullmatch(value.strip()):
        return value.strip()
    return None


def parse_time(value):
    try:
        return datetime.strptime(value, TIME_FORMAT).replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def age_text(seconds):
    if seconds is None:
        return "age unknown"
    if seconds < 120:
        return f"{seconds} s old"
    if seconds < 7200:
        return f"{seconds // 60} min old"
    if seconds < 172800:
        return f"{seconds // 3600} h old"
    return f"{seconds // 86400} days old"


def freshness(snapshot, now=None, max_age_s=MAX_AGE_S, skew_s=CLOCK_SKEW_S):
    """Describe how current a snapshot is; never raises on bad input."""
    now = now or datetime.now(timezone.utc)
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    raw_time = snapshot.get("captured_at")
    captured = parse_time(raw_time)
    age = None
    if raw_time is None:
        state = "unknown_time"
    elif captured is None:
        state = "malformed_time"
    else:
        age = int((now - captured).total_seconds())
        if age < -skew_s:
            state = "future"
        elif age > max_age_s:
            state = "stale"
        else:
            state = "fresh"
            age = max(age, 0)

    current = boot_id(snapshot.get("boot"))
    previous_raw = snapshot.get("previous")
    previous = boot_id(previous_raw.get("boot_id")) if isinstance(previous_raw, dict) else None
    if current is None:
        boot_state = "unknown"
    elif previous is None:
        boot_state = "no_previous"
    elif previous == current:
        boot_state = "same_as_previous"
    else:
        boot_state = "changed_since_previous"

    if state == "fresh":
        summary = f"captured {age_text(age)}"
    elif state == "stale":
        summary = f"STALE: captured {age_text(age)}; Lynx may have changed since"
    elif state == "future":
        summary = (f"CLOCK SKEW: capture time is {age_text(-age).replace(' old', '')} "
                   "in the future; age unknown")
    elif state == "unknown_time":
        summary = "NO CAPTURE TIME: age unknown"
    else:
        summary = "MALFORMED CAPTURE TIME: age unknown"
    if boot_state == "changed_since_previous":
        summary += "; Lynx REBOOTED since the previous snapshot (RAM-loaded drivers are gone)"
    elif boot_state == "unknown":
        summary += "; boot ID unknown"

    return {"state": state, "current": state == "fresh",
            "captured_at": raw_time if isinstance(raw_time, str) else None,
            "age_s": age, "max_age_s": max_age_s,
            "boot_id": current, "previous_boot_id": previous, "boot_state": boot_state,
            "summary": summary}


def attended_boot(entry_boot, snapshot_boot):
    """How an attended entry's boot relates to the snapshot's boot."""
    entry_boot = boot_id(entry_boot)
    if entry_boot is None:
        return "boot_not_recorded"
    if snapshot_boot is None:
        return "snapshot_boot_unknown"
    return "same_boot" if entry_boot == snapshot_boot else "earlier_boot"
