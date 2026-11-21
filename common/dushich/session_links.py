#!/usr/bin/env python3
"""Persistent conversation links between CLI agent sessions and Dushich.

Stores bidirectional links between launcher/tmux sessions and agent
conversation IDs (Codex, Antigravity, Claude Code) in a persistent SQLite
database at ~/.codex/dushich-bridge/session_links.db.

Also maintains the legacy file links at <agent>/private/session-links/<session_id>
for full backward compatibility.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys

import agents

DB_PATH = agents.STATE / "session_links.db"


def _get_db() -> sqlite3.Connection:
    agents.STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    db = sqlite3.connect(str(DB_PATH), timeout=5)
    db.execute("""
        CREATE TABLE IF NOT EXISTS session_links (
            agent TEXT NOT NULL,
            launcher_session TEXT NOT NULL,
            conversation_id TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (agent, launcher_session)
        )
    """)
    db.execute("""
        CREATE INDEX IF NOT EXISTS idx_session_links_conv
        ON session_links (agent, conversation_id)
    """)
    db.execute("""
        CREATE INDEX IF NOT EXISTS idx_session_links_updated
        ON session_links (agent, updated_at DESC)
    """)
    db.commit()
    return db


def set_link(agent_key: str, launcher_session: str, conversation_id: str) -> None:
    """Record a conversation link in SQLite and legacy text file."""
    if not agent_key or not launcher_session or not conversation_id:
        return
    now = datetime.now(timezone.utc).isoformat()
    try:
        with _get_db() as db:
            db.execute("""
                INSERT INTO session_links (agent, launcher_session, conversation_id, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(agent, launcher_session) DO UPDATE SET
                    conversation_id=excluded.conversation_id,
                    updated_at=excluded.updated_at
            """, (agent_key, launcher_session, conversation_id, now))
    except Exception as exc:
        print(f"Warning: could not write session link to DB: {exc}", file=sys.stderr)

    # Legacy file mirror
    try:
        agent = agents.get(agent_key)
        links_dir = agent.home / "private/session-links"
        links_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        tmp = links_dir / f"{launcher_session}.tmp"
        tmp.write_text(conversation_id.strip() + "\n", encoding="utf-8")
        tmp.replace(links_dir / launcher_session)
    except Exception:
        pass


def get_conversation(agent_key: str, launcher_session: str | None) -> str | None:
    """Get active conversation ID for a launcher session."""
    if not agent_key or not launcher_session:
        return None
    try:
        with _get_db() as db:
            row = db.execute("""
                SELECT conversation_id FROM session_links
                WHERE agent = ? AND launcher_session = ?
            """, (agent_key, launcher_session)).fetchone()
            if row and row[0]:
                return row[0]
    except Exception:
        pass

    # Fallback to legacy file
    try:
        agent = agents.get(agent_key)
        link = agent.home / "private/session-links" / launcher_session
        if link.is_file():
            val = link.read_text(encoding="utf-8").strip()
            if val:
                # Cache into DB
                set_link(agent_key, launcher_session, val)
                return val
    except Exception:
        pass

    return None


def get_latest_conversation(agent_key: str) -> str | None:
    """Get most recently updated conversation ID for an agent."""
    if not agent_key:
        return None
    try:
        with _get_db() as db:
            row = db.execute("""
                SELECT conversation_id FROM session_links
                WHERE agent = ?
                ORDER BY updated_at DESC
                LIMIT 1
            """, (agent_key,)).fetchone()
            if row and row[0]:
                return row[0]
    except Exception:
        pass
    return None


def get_launcher_session(agent_key: str, conversation_id: str) -> str | None:
    """Reverse lookup: find launcher session for a conversation ID."""
    if not agent_key or not conversation_id:
        return None
    try:
        with _get_db() as db:
            row = db.execute("""
                SELECT launcher_session FROM session_links
                WHERE agent = ? AND conversation_id = ?
                ORDER BY updated_at DESC
                LIMIT 1
            """, (agent_key, conversation_id)).fetchone()
            if row and row[0]:
                return row[0]
    except Exception:
        pass
    return None


def is_conversation_active_or_linked(agent_key: str, conversation_id: str) -> bool:
    """Check if a conversation ID has ever been linked to a session."""
    if not agent_key or not conversation_id:
        return False
    try:
        with _get_db() as db:
            row = db.execute("""
                SELECT 1 FROM session_links
                WHERE agent = ? AND conversation_id = ?
                LIMIT 1
            """, (agent_key, conversation_id)).fetchone()
            if row:
                return True
    except Exception:
        pass
    return False


def list_links(agent_key: str | None = None) -> list[dict]:
    try:
        with _get_db() as db:
            if agent_key:
                rows = db.execute("""
                    SELECT agent, launcher_session, conversation_id, updated_at
                    FROM session_links WHERE agent = ? ORDER BY updated_at DESC
                """, (agent_key,)).fetchall()
            else:
                rows = db.execute("""
                    SELECT agent, launcher_session, conversation_id, updated_at
                    FROM session_links ORDER BY updated_at DESC
                """).fetchall()
            return [{"agent": r[0], "launcher_session": r[1],
                     "conversation_id": r[2], "updated_at": r[3]} for r in rows]
    except Exception:
        return []


def handle_hook(agent_key: str) -> int:
    """Generic SessionStart hook entry point reading JSON from stdin."""
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}

    agent = agents.get(agent_key)
    launcher = os.environ.get(agent.session_env, "")
    
    # Try different conversation ID field names from various CLIs
    cid = (
        payload.get("conversationId") or
        payload.get("conversation_id") or
        payload.get("session_id") or
        payload.get("sessionId") or
        ""
    )

    if not cid and agent_key == "banshee":
        # Look in workspace presence locks or recent databases
        presence_dir = agents.HOME / ".gemini/antigravity-cli/presence"
        if presence_dir.is_dir():
            locks = sorted(presence_dir.glob("*.lock"), key=lambda p: p.stat().st_mtime, reverse=True)
            if locks:
                cid = locks[0].stem

    if launcher and cid:
        set_link(agent_key, launcher, cid)

    # Antigravity/Claude hooks expect valid JSON on stdout
    print("{}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Persistent session conversation links")
    subs = parser.add_subparsers(dest="action")

    set_p = subs.add_parser("set")
    set_p.add_argument("--agent", required=True, choices=["aria", "banshee", "gwyn"])
    set_p.add_argument("--session", required=True)
    set_p.add_argument("--conversation", required=True)

    get_p = subs.add_parser("get")
    get_p.add_argument("--agent", required=True, choices=["aria", "banshee", "gwyn"])
    get_p.add_argument("--session", required=True)

    subs.add_parser("list")

    hook_p = subs.add_parser("hook")
    hook_p.add_argument("--agent", required=True, choices=["aria", "banshee", "gwyn"])

    args = parser.parse_args()

    if args.action == "set":
        set_link(args.agent, args.session, args.conversation)
        return 0
    elif args.action == "get":
        conv = get_conversation(args.agent, args.session)
        if conv:
            print(conv)
            return 0
        return 1
    elif args.action == "list":
        print(json.dumps(list_links(), indent=2))
        return 0
    elif args.action == "hook":
        return handle_hook(args.agent)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
