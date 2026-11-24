#!/usr/bin/env python3
"""Send a direct chat message from Noob to Lynx.

Appends to thought log, creates high-priority agent job, and emits sense line.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

JOBS = Path("/var/lib/lynx-agent/jobs")
THOUGHT_FILE = Path("/var/lib/noobia/lynx_thought.txt")
SENSE_CMD = "/usr/local/lib/noobia/autonomy/sense.py"


def main():
    if len(sys.argv) < 2:
        print("Usage: lynx-chat-send <message>", file=sys.stderr)
        return 1
    msg = " ".join(sys.argv[1:]).strip()
    if not msg:
        return 0

    # 1. Update thought file
    try:
        THOUGHT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with THOUGHT_FILE.open("a", encoding="utf-8") as f:
            f.write(f"Noob: {msg}\n")
    except Exception:
        pass

    # 2. Directly create agent job so Lynx replies immediately
    try:
        sys.path.insert(0, "/usr/local/lib/noobia/autonomy")
        sys.path.insert(0, "/usr/local/share/lynx/agent")
        from lynx_agent_queue import JobQueue

        prompt = f"CHAT: {msg}"   # Tom 2026-11-24; what CHAT: means is in her instructions
        JobQueue(JOBS).create_job(prompt)
    except Exception as exc:
        print(f"Failed to queue agent job: {exc}", file=sys.stderr)

    # 3. Emit sense line for telemetry (non-blocking)
    try:
        if Path(SENSE_CMD).is_file():
            subprocess.Popen(
                ["/usr/bin/python3", SENSE_CMD, "1", "chat", "message", "author=Noob", "-t", msg],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
