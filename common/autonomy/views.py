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
        self._file_inode: int | None = None
        self._journal_cursor: str | None = None

        if start_at_end:
            if self.backend in ("file", "fallback") and self.log_file.exists():
                try:
                    st = self.log_file.stat()
                    self._file_offset = st.st_size
                    self._file_inode = st.st_ino
                except OSError:
                    self._file_offset = 0
                    self._file_inode = None

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
        for raw in all_lines:
            payload = self.parse_syslog_line(raw)
            if payload is not None:
                matched.append(payload)
        return matched[-lines:]

    def _read_new_file(self) -> list[str]:
        if not self.log_file.exists():
            return []
        try:
            st = self.log_file.stat()
            size = st.st_size
            inode = st.st_ino

            # F4: detect rotation by inode change as well as shrink
            if self._file_inode is not None and inode != self._file_inode:
                self._file_offset = 0
            elif size < self._file_offset:
                self._file_offset = 0
            self._file_inode = inode

            # F3: open file in binary mode and keep byte offsets
            with open(self.log_file, "rb") as f:
                f.seek(self._file_offset)
                chunk = f.read()

            if not chunk:
                return []

            # F1: SPLIT LINES - consume only up to the last newline
            last_nl = chunk.rfind(b"\n")
            if last_nl == -1:
                return []

            consumed = chunk[:last_nl + 1]
            self._file_offset += len(consumed)

            text = consumed.decode("utf-8", errors="replace")
            new_lines = text.splitlines()
        except OSError:
            return []

        matched = []
        for raw in new_lines:
            payload = self.parse_syslog_line(raw)
            if payload is not None:
                matched.append(payload)
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
        # F2: Strict tag match (BSD, ISO-8601, or no header) with optional PID, zero loop risk
        pattern = re.compile(
            rf"^(?:(?:[A-Za-z]{{3}}\s+\d+\s+\d{{2}}:\d{{2}}:\d{{2}}|\d{{4}}-\d{{2}}-\d{{2}}[T\s]\d{{2}}:\d{{2}}:\d{{2}}(?:\.\d+)?(?:Z|[+-]\d{{2}}:?\d{{2}})?)(?:\s+\S+){{0,2}}\s+)?{re.escape(self.view)}(?:\[\d+\])?:\s*(.*)$"
        )
        m = pattern.match(line.strip())
        if m:
            return m.group(1).strip()
        return None
