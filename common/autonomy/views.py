"""Log views and readers for Noobia autonomy (ARCHITECTURE.md §3).

Deliverable A, task E2.

Views:
- noobia-sense: sense services -> the trigger (strictly isolated)
- noobia-autonomy: trigger, ranker, and router decisions
- noobia-aigel: Aigel's messages and decisions
- noobia-agent: Noob's own actions (never read by the trigger)

Backends:
- journald (systemd hosts like Nexus)
- BusyBox file backend (/var/log/lynx/messages or custom path)
- Fallback in-memory/file backend
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Generator

KNOWN_VIEWS = ("noobia-sense", "noobia-autonomy", "noobia-aigel", "noobia-agent")
BUSYBOX_SYSLOG_PATH = Path("/var/log/lynx/messages")


class ViewError(Exception):
    pass


class ViewReader:
    def __init__(
        self,
        view: str,
        backend: str = "auto",
        log_file: Path | str | None = None,
    ):
        if view not in KNOWN_VIEWS and not re.match(r"^[a-z0-9_-]{1,32}\Z", view):
            raise ViewError(f"invalid view name: {view!r}")
        self.view = view
        self.log_file = Path(log_file) if log_file else BUSYBOX_SYSLOG_PATH

        if backend == "auto":
            if shutil.which("journalctl") is not None:
                self.backend = "journald"
            elif self.log_file.exists():
                self.backend = "file"
            else:
                self.backend = "fallback"
        else:
            if backend not in ("journald", "file", "fallback"):
                raise ViewError(f"unknown backend: {backend!r}")
            self.backend = backend

    def read_recent(self, lines: int = 100) -> list[str]:
        """Read up to `lines` recent entries for this view."""
        if lines <= 0:
            return []

        if self.backend == "journald":
            return self._read_journald(lines)
        elif self.backend == "file":
            return self._read_file(lines)
        else:
            return self._read_fallback(lines)

    def _read_journald(self, lines: int) -> list[str]:
        cmd = ["journalctl", "-t", self.view, "-n", str(lines), "-o", "cat", "--no-pager"]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5.0)
            if res.returncode == 0:
                raw_lines = [l.strip() for l in res.stdout.splitlines() if l.strip()]
                return raw_lines
        except Exception:
            pass
        return []

    def _read_file(self, lines: int) -> list[str]:
        if not self.log_file.exists():
            return []
        try:
            with open(self.log_file, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
        except OSError:
            return []

        matched = []
        pattern = re.compile(rf"(?:^|[\s:]){re.escape(self.view)}:\s*(.*)$")
        for raw in all_lines:
            m = pattern.search(raw)
            if m:
                matched.append(m.group(1).strip() if m.group(1).strip() else raw.strip())
            elif self.view in raw:
                matched.append(raw.strip())
        return matched[-lines:]

    def _read_fallback(self, lines: int) -> list[str]:
        if self.log_file and self.log_file.exists():
            return self._read_file(lines)
        return []

    def parse_syslog_line(self, line: str) -> str | None:
        """Extract view message payload from a raw syslog line if it matches this view."""
        pattern = re.compile(rf"(?:^|[\s:]){re.escape(self.view)}:\s*(.*)$")
        m = pattern.search(line)
        if m:
            return m.group(1).strip()
        return None
