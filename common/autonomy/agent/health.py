"""Read-only privacy and queue health monitoring for any Noob's agent (NA-81)."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import time
from typing import Any, Dict, List, Optional, Set

JOB = re.compile(r"[0-9a-f]{32}\.(pending|running|done)\Z")
OUTBOX = re.compile(r"[0-9a-f]{32}\.reply(\.bad)?\Z")


def snapshot(root: Path | str, stop: Path | str, now: Optional[float] = None, owner: Optional[int] = None) -> Dict[str, Any]:
    root_p, stop_p = Path(root), Path(stop)
    now_ts = time.time() if now is None else now
    counts = {"pending": 0, "running": 0, "done": 0}
    issues: Set[str] = set()
    oldest: Optional[int] = None
    try:
        directory = root_p.lstat()
    except OSError:
        issues.add("queue_unavailable")
    else:
        if not stat.S_ISDIR(directory.st_mode) or \
                stat.S_IMODE(directory.st_mode) != 0o700 or \
                (owner is not None and directory.st_uid != owner):
            issues.add("queue_not_private")
        if stat.S_ISDIR(directory.st_mode):
            try:
                with os.scandir(root_p) as entries:
                    for entry in entries:
                        try:
                            metadata = entry.stat(follow_symlinks=False)
                        except OSError:
                            issues.add("entry_unreadable")
                            continue
                        match = JOB.fullmatch(entry.name)
                        if entry.name == ".lock":
                            kind = None
                        elif match:
                            kind = match.group(1) if stat.S_ISREG(metadata.st_mode) else None
                            if kind:
                                counts[kind] += 1
                        elif OUTBOX.fullmatch(entry.name):
                            kind = None
                        else:
                            kind = None
                            issues.add("unexpected_entry")
                        if not stat.S_ISREG(metadata.st_mode) or \
                                stat.S_IMODE(metadata.st_mode) != 0o600 or \
                                (owner is not None and metadata.st_uid != owner):
                            issues.add("entry_not_private")
                        if kind == "pending":
                            age = max(0, int(now_ts - metadata.st_mtime))
                            oldest = age if oldest is None else max(oldest, age)
            except OSError:
                issues.add("queue_unreadable")
    stopped = False
    try:
        marker = stop_p.lstat()
    except FileNotFoundError:
        pass
    except OSError:
        issues.add("stop_marker_unreadable")
    else:
        stopped = True
        if not stat.S_ISREG(marker.st_mode) or \
                stat.S_IMODE(marker.st_mode) != 0o600 or \
                (owner is not None and marker.st_uid != owner):
            issues.add("stop_marker_not_private")
    return {
        "counts": counts,
        "oldest_pending_seconds": oldest,
        "stopped": stopped,
        "issues": sorted(issues),
    }


def agent_health(queue_root: Path | str, stop_path: Path | str) -> Dict[str, Any]:
    return snapshot(root=queue_root, stop=stop_path)
