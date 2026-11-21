"""Pattern database for structured ranker patterns (ARCHITECTURE.md §4).

Maintains a SQLite database of structured regex / match patterns per host.
Provides indexed lookup by host (primary index) and output_message (secondary index),
tracks hit counts, and selects the top dynamic patterns for the host's ranker:
    SELECT * FROM patterns WHERE host = ? ORDER BY count DESC, id DESC LIMIT 100
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from typing import Any

DEFAULT_DB_PATH = Path(os.environ.get("NOOBIA_PATTERNS_DB", "/noobia/aigel/private/patterns.db"))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class PatternDB:
    """SQLite pattern database with host and output_message indexes."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pattern_id TEXT NOT NULL UNIQUE,
                    host TEXT NOT NULL,
                    sense TEXT NOT NULL,
                    event TEXT NOT NULL,
                    fields_json TEXT,
                    text_contains TEXT,
                    regex TEXT,
                    output_message TEXT,
                    to_noob INTEGER DEFAULT 1,
                    p INTEGER DEFAULT 1,
                    cooldown_s INTEGER DEFAULT 300,
                    count INTEGER DEFAULT 0,
                    must_examples TEXT,
                    must_not_examples TEXT,
                    origin TEXT DEFAULT 'aigel',
                    created_at TEXT NOT NULL,
                    last_hit_at TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_patterns_host ON patterns(host)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_patterns_message ON patterns(output_message)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_patterns_host_count ON patterns(host, count DESC, id DESC)")

    def upsert_pattern(self, pattern: dict[str, Any], host: str = "lynx", initial_count: int = 1) -> bool:
        """Insert or update a structured pattern from Aigel or operator."""
        pattern_id = pattern.get("id")
        if not pattern_id or not isinstance(pattern_id, str):
            return False

        match = pattern.get("match", {})
        sense = match.get("sense", "")
        event = match.get("event", "")
        if not sense or not event:
            return False

        fields_json = json.dumps(match.get("fields")) if match.get("fields") is not None else None
        text_contains = match.get("text_contains")
        regex = pattern.get("regex")
        output_message = pattern.get("message")
        to_noob = 1 if pattern.get("to_noob", True) else 0
        p = int(pattern.get("p", 1))
        cooldown_s = int(pattern.get("cooldown_s", 300))
        origin = pattern.get("origin", "aigel")
        count_init = max(1, int(initial_count))

        examples = pattern.get("examples", {})
        must_ex = json.dumps(examples.get("must", []))
        must_not_ex = json.dumps(examples.get("must_not", []))
        now = _utc_now_iso()

        with self._connect() as conn:
            conn.execute("""
                INSERT INTO patterns (
                    pattern_id, host, sense, event, fields_json, text_contains, regex,
                    output_message, to_noob, p, cooldown_s, count, must_examples,
                    must_not_examples, origin, created_at, last_hit_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                ON CONFLICT(pattern_id) DO UPDATE SET
                    host = excluded.host,
                    sense = excluded.sense,
                    event = excluded.event,
                    fields_json = excluded.fields_json,
                    text_contains = excluded.text_contains,
                    regex = excluded.regex,
                    output_message = excluded.output_message,
                    to_noob = excluded.to_noob,
                    p = excluded.p,
                    cooldown_s = excluded.cooldown_s,
                    count = patterns.count + 1,
                    must_examples = excluded.must_examples,
                    must_not_examples = excluded.must_not_examples,
                    origin = excluded.origin
            """, (
                pattern_id, host, sense, event, fields_json, text_contains, regex,
                output_message, to_noob, p, cooldown_s, count_init, must_ex, must_not_ex, origin, now
            ))
        return True

    def record_hit(self, pattern_id: str) -> bool:
        """Increment hit count and update last_hit_at."""
        now = _utc_now_iso()
        with self._connect() as conn:
            cur = conn.execute("""
                UPDATE patterns
                SET count = count + 1, last_hit_at = ?
                WHERE pattern_id = ?
            """, (now, pattern_id))
            return cur.rowcount > 0

    def get_top_ranker_patterns(self, host: str, limit: int = 100, require_hits: bool = False) -> list[dict[str, Any]]:
        """Return the top patterns for host's ranker, ordered by count DESC."""
        where_sql = "WHERE host = ? AND count > 0" if require_hits else "WHERE host = ?"
        with self._connect() as conn:
            cur = conn.execute(f"""
                SELECT * FROM patterns
                {where_sql}
                ORDER BY count DESC, id DESC
                LIMIT ?
            """, (host, limit))
            rows = cur.fetchall()

        out = []
        for r in rows:
            match = {"sense": r["sense"], "event": r["event"]}
            if r["fields_json"]:
                try:
                    match["fields"] = json.loads(r["fields_json"])
                except ValueError:
                    pass
            if r["text_contains"]:
                match["text_contains"] = r["text_contains"]

            pat: dict[str, Any] = {
                "id": r["pattern_id"],
                "match": match,
                "message": r["output_message"],
                "to_noob": bool(r["to_noob"]),
                "p": r["p"],
                "cooldown_s": r["cooldown_s"],
                "hits": r["count"],
                "last_hit": r["last_hit_at"],
                "origin": r["origin"],
                "added_at": r["created_at"],
            }
            if r["regex"]:
                pat["regex"] = r["regex"]
            examples = {}
            if r["must_examples"]:
                try:
                    examples["must"] = json.loads(r["must_examples"])
                except ValueError:
                    pass
            if r["must_not_examples"]:
                try:
                    examples["must_not"] = json.loads(r["must_not_examples"])
                except ValueError:
                    pass
            if examples:
                pat["examples"] = examples
            out.append(pat)
        return out

    def count_patterns(self, host: str) -> int:
        with self._connect() as conn:
            cur = conn.execute("SELECT COUNT(*) FROM patterns WHERE host = ?", (host,))
            return cur.fetchone()[0]

    def list_patterns(self, host: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if host:
                cur = conn.execute("SELECT * FROM patterns WHERE host = ? ORDER BY count DESC, id DESC", (host,))
            else:
                cur = conn.execute("SELECT * FROM patterns ORDER BY host ASC, count DESC, id DESC")
            rows = cur.fetchall()
        return [dict(r) for r in rows]
