#!/usr/bin/env python3
"""View writer for Aigel (ARCHITECTURE.md section 3: views).

Aigel's decisions and messages belong to the ``noobia-aigel`` view,
where people and the Noob's history can read them. On systemd hosts
the lines go through ``logger -t <view>`` so ``journalctl -t <view>``
sees them; when no syslog route is available (or when tests ask for
it) the same lines are appended to a bounded file under
``aigel/logs/views/``.

Rules followed here:
- one line per record, bounded in length;
- view files are bounded in size (never grow without limit, section 9);
- logging must never crash the decision path.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

NOOBIA = os.environ.get("NOOBIA", "/noobia")
DEFAULT_VIEW_DIR = NOOBIA + "/aigel/logs/views"
KNOWN_VIEWS = ("noobia-sense", "noobia-autonomy", "noobia-aigel", "noobia-agent")

MAX_LINE_CHARS = 1024
MAX_FILE_BYTES = 1_000_000  # 1 MiB per view file


class ViewLogger:
    """Write bounded one-line records to a Noobia view."""

    def __init__(
        self,
        view: str,
        file_dir: str | Path | None = None,
        force_file: bool = False,
        logger_timeout_s: float = 5.0,
    ):
        if view not in KNOWN_VIEWS:
            raise ValueError(f"unknown view: {view!r}")
        self.view = view
        self.file_dir = Path(file_dir) if file_dir else Path(DEFAULT_VIEW_DIR)
        self.force_file = force_file or os.environ.get("AIGEL_FORCE_FILE_LOG") == "1"
        self.logger_timeout_s = float(logger_timeout_s)
        self.use_logger = (not self.force_file) and shutil.which("logger") is not None

    def write(self, line: str) -> None:
        line = " ".join(str(line).split())  # one line, no newlines
        if len(line) > MAX_LINE_CHARS:
            line = line[:MAX_LINE_CHARS]
        if self.use_logger:
            try:
                subprocess.run(
                    ["logger", "-t", self.view, line],
                    check=True,
                    timeout=self.logger_timeout_s,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return
            except (subprocess.SubprocessError, OSError):
                pass  # fall through to the file route
        self._write_file(line)

    def _write_file(self, line: str) -> None:
        try:
            self.file_dir.mkdir(parents=True, exist_ok=True)
            path = self.file_dir / f"{self.view}.log"
            if path.exists() and path.stat().st_size > MAX_FILE_BYTES:
                return  # bounded: stop growing, never queue unboundedly
            ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            with path.open("a", encoding="utf-8") as fh:
                fh.write(f"{ts} aigel({self.view}): {line}\n")
        except OSError:
            pass  # logging must never take Aigel down
