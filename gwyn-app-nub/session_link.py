#!/usr/bin/env python3
"""SessionStart hook: remember which Claude Code transcript a Gwyn launcher session uses.

The launcher starts Claude Code with --session-id equal to its tmux session ID,
but /resume or --continue inside Claude Code switches to another transcript.
Claude Code passes the real session_id to SessionStart hooks on start and
resume; this writes it to the persistent session_links DB and private/session-links/<launcher session>
so the Dushich bridge always reads the conversation actually on screen.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys

NOOBIA = Path(os.environ.get("NOOBIA", "/noobia"))
sys.path.insert(0, str(NOOBIA / "common/dushich"))

try:
    import session_links
except ImportError:
    session_links = None

LINKS = NOOBIA / "gwyn-app-nub/private/session-links"
UUID = re.compile(r"^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$")


def main() -> int:
    launcher = os.environ.get("NOOBIA_GWYN_SESSION", "")
    try:
        data = json.load(sys.stdin)
        session = data.get("session_id", "")
    except (json.JSONDecodeError, AttributeError):
        return 0
    if not (UUID.fullmatch(launcher) and UUID.fullmatch(session)):
        return 0  # --plain sessions have no launcher session; nothing to link
    
    if session_links is not None:
        session_links.set_link("gwyn", launcher, session)
    else:
        LINKS.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = LINKS / (launcher + ".tmp")
        temporary.write_text(session + "\n")
        temporary.replace(LINKS / launcher)
    return 0


if __name__ == "__main__":
    sys.exit(main())
