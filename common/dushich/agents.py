"""Who can talk to Dushich, and where each agent's pieces live.

One row per cloud agent. The bridge, MCP adapter, and helper threads read this
table instead of hard-coding an agent, so adding an agent means adding a row
(and, for a new CLI, a transcript reader).
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

NOOBIA = Path(os.environ.get("NOOBIA", "/noobia"))
HOME = Path(os.environ.get("HOME", "/home/aria"))
DUSHICH_CODING = NOOBIA / "dushich/coding"
STATE = HOME / ".codex/dushich-bridge"          # shared helper/explore state
TASK_RUNS = DUSHICH_CODING / "private/codex/task-runs"


@dataclass(frozen=True)
class Agent:
    key: str             # command-line name: aria, banshee, gwyn
    name: str            # how Dushich and the human see the agent
    home: Path           # /noobia/<agent>
    files_root: Path     # files the agent may attach to a handoff
    session_env: str     # environment variable holding the launcher session ID
    conversation_env: str
    transcript: str      # module that reads the CLI's visible dialogue
    helper: str          # module that answers dushich_ask
    ask_timeout: int     # seconds; the first question in a long conversation is slow

    @property
    def task_runs(self) -> Path:
        return self.home / "private/task-runs"

    @property
    def launcher(self) -> Path:
        return self.home / "launch"

    @property
    def review_status(self) -> str:
        return f"needs_{self.key}"


AGENTS = {
    "banshee": Agent("banshee", "Banshee", NOOBIA / "banshee", NOOBIA / "banshee/workspace",
                     "NOOBIA_BANSHEE_SESSION", "NOOBIA_BANSHEE_CONVERSATION_ID",
                     "transcript_antigravity", "helper_banshee", 200),
    "gwyn": Agent("gwyn", "Gwyn", NOOBIA / "gwyn-app-nub", NOOBIA / "gwyn-app-nub",
                  "NOOBIA_GWYN_SESSION", "NOOBIA_GWYN_CONVERSATION_ID",
                  "transcript_claude", "helper_gwyn", 400),
}
# Aria's Codex bridge (aria/dushich-bridge) predates this table and keeps its
# own engine; mcp.py drives it through its command line.
ARIA = NOOBIA / "aria"


def get(key: str) -> Agent:
    try:
        return AGENTS[key]
    except KeyError:
        raise ValueError(f"Unknown agent {key!r}; known: {', '.join(AGENTS)}") from None
