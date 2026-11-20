#!/usr/bin/env python3
"""Read a fresh Codex TUI session ID using its local /status command."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys
import time
import os

HOME = os.path.expanduser("~")


UUID = re.compile(r"^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$")
TMUX = re.compile(r"^noobia-aria-[A-Za-z0-9-]+$")
LOCKS = Path(HOME + "/.codex/thread-writer-locks")


def recent_lock_session(started_at: float) -> str | None:
    try:
        locks = sorted(LOCKS.glob("*.lock"), key=lambda p: p.stat().st_mtime, reverse=True)
        for lock in locks:
            if lock.stat().st_mtime >= started_at - 2.0 and UUID.fullmatch(lock.stem):
                return lock.stem
    except OSError:
        pass
    return None


def capture(pane: str) -> str:
    result = subprocess.run(
        ["tmux", "capture-pane", "-p", "-J", "-S", "-120", "-t", pane],
        capture_output=True, text=True, check=True,
    )
    return result.stdout


def session_id(screen: str) -> str | None:
    if "Session:" not in screen:
        return None
    section = screen.rsplit("Session:", 1)[1]
    pieces = []
    for line in section.splitlines():
        part = line.strip()
        if not part:
            continue
        if not re.fullmatch(r"[0-9a-f-]+", part):
            if pieces:
                break
            continue
        pieces.append(part)
        candidate = "".join(pieces)
        if UUID.fullmatch(candidate):
            return candidate
        if len(candidate) >= 36:
            break
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tmux_session")
    args = parser.parse_args()
    if not TMUX.fullmatch(args.tmux_session):
        parser.error("invalid tmux session")
    pane = f"{args.tmux_session}:0.0"
    started_at = time.time()
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            screen = capture(pane)
        except subprocess.CalledProcessError:
            time.sleep(0.2)
            continue
        if "Update available" in screen:
            subprocess.run(["tmux", "send-keys", "-t", pane, "Escape"], check=False)
            time.sleep(0.4)
            continue
        if "Ask Codex to do anything" in screen:
            break
        time.sleep(0.2)
    else:
        lock_id = recent_lock_session(started_at)
        if lock_id:
            print(lock_id)
            return 0
        print("Codex prompt did not appear", file=sys.stderr)
        return 1
    lock_id = recent_lock_session(started_at)
    if lock_id:
        print(lock_id)
        return 0
    subprocess.run(["tmux", "send-keys", "-t", pane, "-l", "/status"], check=True)
    time.sleep(0.2)
    for _ in range(2):
        subprocess.run(["tmux", "send-keys", "-t", pane, "Enter"], check=True)
        until = time.monotonic() + 2
        while time.monotonic() < until:
            found = session_id(capture(pane))
            if found:
                subprocess.run(["tmux", "send-keys", "-t", pane, "Escape"], check=True)
                print(found)
                return 0
            time.sleep(0.2)
    print("Could not read Codex session ID from /status", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
