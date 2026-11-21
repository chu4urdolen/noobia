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
import time
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
        start_at_end: bool = False,
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

        self._file_offset: int = 0
        self._journal_cursor: str | None = None

        if start_at_end:
            if self.backend in ("file", "fallback") and self.log_file.exists():
                try:
                    self._file_offset = self.log_file.stat().st_size
                except OSError:
                    self._file_offset = 0

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

    def read_new(self) -> list[str]:
        """Read only newly arrived lines since last call (V1 view follower)."""
        if self.backend == "journald":
            return self._read_new_journald()
        elif self.backend == "file":
            return self._read_new_file()
        else:
            return self._read_new_fallback()

    def follow(self, poll_interval_s: float = 1.0, stop=lambda: False) -> Generator[str, None, None]:
        """Generator yielding new lines as they arrive."""
        while not stop():
            new_lines = self.read_new()
            for line in new_lines:
                yield line
            time.sleep(poll_interval_s)

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

    def _read_new_journald(self) -> list[str]:
        cmd = ["journalctl", "-t", self.view, "-o", "json", "--no-pager"]
        if self._journal_cursor:
            cmd.extend(["--after-cursor", self._journal_cursor])
        else:
            cmd.extend(["-n", "100"])

        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5.0)
            if res.returncode != 0:
                return []
            lines = []
            for raw_line in res.stdout.splitlines():
                if not raw_line.strip():
                    continue
                try:
                    entry = json.loads(raw_line)
                    cursor = entry.get("__CURSOR")
                    if cursor:
                        self._journal_cursor = cursor
                    msg = entry.get("MESSAGE", "").strip()
                    if msg:
                        lines.append(msg)
                except Exception:
                    pass
            return lines
        except Exception:
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

    def _read_new_file(self) -> list[str]:
        if not self.log_file.exists():
            return []
        try:
            size = self.log_file.stat().st_size
            if size < self._file_offset:
                # Log rotation detected; reset offset to 0
                self._file_offset = 0

            with open(self.log_file, "r", encoding="utf-8", errors="replace") as f:
                f.seek(self._file_offset)
                new_chunk = f.readlines()
                self._file_offset = f.tell()
        except OSError:
            return []

        matched = []
        pattern = re.compile(rf"(?:^|[\s:]){re.escape(self.view)}:\s*(.*)$")
        for raw in new_chunk:
            m = pattern.search(raw)
            if m:
                matched.append(m.group(1).strip() if m.group(1).strip() else raw.strip())
            elif self.view in raw:
                matched.append(raw.strip())
        return matched

    def _read_fallback(self, lines: int) -> list[str]:
        if self.log_file and self.log_file.exists():
            return self._read_file(lines)
        return []

    def _read_new_fallback(self) -> list[str]:
        if self.log_file and self.log_file.exists():
            return self._read_new_file()
        return []

    def parse_syslog_line(self, line: str) -> str | None:
        """Extract view message payload from a raw syslog line if it matches this view."""
        pattern = re.compile(rf"(?:^|[\s:]){re.escape(self.view)}:\s*(.*)$")
        m = pattern.search(line)
        if m:
            return m.group(1).strip()
        return None
