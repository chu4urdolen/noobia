"""Durable SQLite Event Store for Autonomous Noobs (Section 3.1 & NA-10).

Provides:
- SQLite WAL mode durable event persistence.
- Unique event IDs: <noob>-<boot>-<seq>.
- States: captured, ignored, unresolved, delivered, acked.
- Capacity monitoring & cleanup safeguards.
- Contract adherence: Zero event loss across restarts or busy GPU queues.
"""

from __future__ import annotations

import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class EventRecord:
    event_id: str
    timestamp: float
    raw_text: str
    state: str  # captured, ignored, unresolved, delivered, acked
    origin: str  # host or sense name
    priority: int = 0
    reason: Optional[str] = None
    batch_id: Optional[str] = None


class EventStore:
    def __init__(self, db_path: str | Path, noob_name: str = "lynx", boot_id: Optional[str] = None):
        self.db_path = Path(db_path)
        self.noob_name = noob_name
        self.boot_id = boot_id or hex(int(time.time()))[2:]
        self._seq = 0
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    timestamp REAL NOT NULL,
                    raw_text TEXT NOT NULL,
                    state TEXT NOT NULL,
                    origin TEXT NOT NULL,
                    priority INTEGER DEFAULT 0,
                    reason TEXT,
                    batch_id TEXT,
                    created_at REAL NOT NULL
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_state ON events (state);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON events (timestamp);")
            
            # Find highest sequence for current boot
            cur = conn.execute(
                "SELECT event_id FROM events WHERE event_id LIKE ? ORDER BY rowid DESC LIMIT 1;",
                (f"{self.noob_name}-{self.boot_id}-%",)
            )
            row = cur.fetchone()
            if row:
                try:
                    self._seq = int(row[0].split("-")[-1])
                except (ValueError, IndexError):
                    self._seq = 0

    def generate_id(self) -> str:
        self._seq += 1
        return f"{self.noob_name}-{self.boot_id}-{self._seq:08d}"

    def capture(self, raw_text: str, origin: str, priority: int = 0, state: str = "captured", reason: Optional[str] = None) -> EventRecord:
        """Atomically persist a raw event before any downstream processing."""
        event_id = self.generate_id()
        now = time.time()
        record = EventRecord(
            event_id=event_id,
            timestamp=now,
            raw_text=raw_text,
            state=state,
            origin=origin,
            priority=priority,
            reason=reason
        )
        with self._get_connection() as conn:
            conn.execute(
                """INSERT INTO events (event_id, timestamp, raw_text, state, origin, priority, reason, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?);""",
                (record.event_id, record.timestamp, record.raw_text, record.state, record.origin, record.priority, record.reason, now)
            )
        return record

    def mark_ignored(self, event_id: str, reason: str) -> None:
        """Mark an event as explicitly ignored (touch debounce, duplicate, etc.)."""
        with self._get_connection() as conn:
            conn.execute("UPDATE events SET state = 'ignored', reason = ? WHERE event_id = ?;", (reason, event_id))

    def mark_delivered(self, event_ids: List[str], batch_id: str) -> None:
        """Mark a list of events as dispatched to an inference window."""
        if not event_ids:
            return
        with self._get_connection() as conn:
            conn.executemany(
                "UPDATE events SET state = 'delivered', batch_id = ? WHERE event_id = ?;",
                [(batch_id, eid) for eid in event_ids]
            )

    def ack(self, event_ids: List[str]) -> None:
        """Acknowledge completed processing by the agent worker."""
        if not event_ids:
            return
        with self._get_connection() as conn:
            conn.executemany("UPDATE events SET state = 'acked' WHERE event_id = ?;", [(eid,) for eid in event_ids])

    def get_pending(self, limit: int = 100) -> List[EventRecord]:
        """Fetch unhandled events (captured, delivered but unacknowledged)."""
        with self._get_connection() as conn:
            cur = conn.execute(
                """SELECT event_id, timestamp, raw_text, state, origin, priority, reason, batch_id
                   FROM events WHERE state IN ('captured', 'delivered') ORDER BY rowid ASC LIMIT ?;""",
                (limit,)
            )
            rows = cur.fetchall()
            return [
                EventRecord(
                    event_id=r[0], timestamp=r[1], raw_text=r[2], state=r[3],
                    origin=r[4], priority=r[5], reason=r[6], batch_id=r[7]
                )
                for r in rows
            ]

    def count_by_state(self) -> Dict[str, int]:
        with self._get_connection() as conn:
            cur = conn.execute("SELECT state, COUNT(*) FROM events GROUP BY state;")
            return dict(cur.fetchall())
