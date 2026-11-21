#!/usr/bin/env python3
"""SessionStart hook for Banshee (Antigravity CLI).

When Antigravity starts or resumes a conversation, this hook is invoked by the
Antigravity lifecycle hook runner. It receives the conversation metadata on stdin,
extracts the conversationId, and links it to the active NOOBIA_BANSHEE_SESSION
in the persistent session_links DB.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys

NOOBIA = Path(os.environ.get("NOOBIA", "/noobia"))
sys.path.insert(0, str(NOOBIA / "common/dushich"))

import session_links


if __name__ == "__main__":
    sys.exit(session_links.handle_hook("banshee"))
