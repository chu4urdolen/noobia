"""Personal Notes Database with FTS5 Full-Text Search (NA-61).

Schema:
- notes (id TEXT PRIMARY KEY, ts REAL, text TEXT, tags TEXT, processed INTEGER)
- notes_fts virtual table using FTS5 for local search.
"""

from __future__ import annotations

import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class NoteRecord:
    id: str
    ts: float
    text: str
    tags: str
    processed: bool


class NotesDB:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS notes (
                    id TEXT PRIMARY KEY,
                    ts REAL NOT NULL,
                    text TEXT NOT NULL,
                    tags TEXT DEFAULT '',
                    processed INTEGER DEFAULT 0
                );
            """)
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
                    id UNINDEXED,
                    text,
                    tags,
                    content='notes',
                    content_rowid='rowid'
                );
            """)
            # Triggers to keep FTS in sync
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
                    INSERT INTO notes_fts(rowid, id, text, tags) VALUES (new.rowid, new.id, new.text, new.tags);
                END;
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes BEGIN
                    INSERT INTO notes_fts(notes_fts, rowid, id, text, tags) VALUES('delete', old.rowid, old.id, old.text, old.tags);
                END;
            """)

    def add_note(self, text: str, tags: str = "", note_id: Optional[str] = None) -> str:
        nid = note_id or f"note-{int(time.time())}-{uuid.uuid4().hex[:6]}"
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO notes (id, ts, text, tags, processed) VALUES (?, ?, ?, ?, 0);",
                (nid, now, text.strip(), tags.strip())
            )
        return nid

    def search(self, query: str, limit: int = 20) -> List[NoteRecord]:
        """Full-text search using FTS5."""
        with self._get_connection() as conn:
            cur = conn.execute(
                """SELECT n.id, n.ts, n.text, n.tags, n.processed
                   FROM notes_fts f
                   JOIN notes n ON n.rowid = f.rowid
                   WHERE notes_fts MATCH ?
                   ORDER BY rank LIMIT ?;""",
                (query, limit)
            )
            return [
                NoteRecord(id=r[0], ts=r[1], text=r[2], tags=r[3], processed=bool(r[4]))
                for r in cur.fetchall()
            ]

    def get_unprocessed(self, limit: int = 100) -> List[NoteRecord]:
        with self._get_connection() as conn:
            cur = conn.execute(
                "SELECT id, ts, text, tags, processed FROM notes WHERE processed = 0 ORDER BY ts ASC LIMIT ?;",
                (limit,)
            )
            return [
                NoteRecord(id=r[0], ts=r[1], text=r[2], tags=r[3], processed=bool(r[4]))
                for r in cur.fetchall()
            ]

    def mark_processed(self, note_ids: List[str]) -> None:
        if not note_ids:
            return
        with self._get_connection() as conn:
            conn.executemany("UPDATE notes SET processed = 1 WHERE id = ?;", [(nid,) for nid in note_ids])
