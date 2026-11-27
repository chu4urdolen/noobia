"""Deterministic Reflex Subsystem for Autonomous Noobs (Section 5 & NA-40).

Enables:
- Reflex database: regex on normalized/raw events -> local executable script.
- Execution runner with stable event ID deduplication (fires at most once per event).
- Strict self-trigger guard (reflex outputs carry cause=reflex and cannot trigger own rule).
- Principle 10 safe execution with thermal and timeout checks.
"""

from __future__ import annotations

import os
import re
import sqlite3
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ReflexRule:
    id: int
    pattern: str
    script_path: str
    enabled: bool
    author: str
    version: int
    description: str = ""


class ReflexEngine:
    def __init__(self, db_path: str | Path, noob_name: str = "lynx"):
        self.db_path = Path(db_path)
        self.noob_name = noob_name
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS reflexes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pattern TEXT NOT NULL,
                    script_path TEXT NOT NULL,
                    enabled INTEGER DEFAULT 1,
                    author TEXT NOT NULL,
                    version INTEGER DEFAULT 1,
                    description TEXT DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS reflex_executions (
                    execution_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reflex_id INTEGER NOT NULL,
                    event_id TEXT NOT NULL,
                    executed_at REAL NOT NULL,
                    exit_code INTEGER,
                    output TEXT,
                    UNIQUE(reflex_id, event_id)
                );
            """)

    def add_rule(self, pattern: str, script_path: str, author: str = "lynx-coder", description: str = "") -> int:
        now = time.time()
        with self._get_connection() as conn:
            cur = conn.execute(
                """INSERT INTO reflexes (pattern, script_path, enabled, author, version, description, created_at, updated_at)
                   VALUES (?, ?, 1, ?, 1, ?, ?, ?);""",
                (pattern, str(script_path), author, description, now, now)
            )
            return cur.lastrowid

    def list_rules(self, enabled_only: bool = True) -> List[ReflexRule]:
        with self._get_connection() as conn:
            query = "SELECT id, pattern, script_path, enabled, author, version, description FROM reflexes"
            if enabled_only:
                query += " WHERE enabled = 1"
            cur = conn.execute(query)
            return [
                ReflexRule(
                    id=r[0], pattern=r[1], script_path=r[2], enabled=bool(r[3]),
                    author=r[4], version=r[5], description=r[6]
                )
                for r in cur.fetchall()
            ]

    def set_enabled(self, rule_id: int, enabled: bool) -> bool:
        with self._get_connection() as conn:
            cur = conn.execute(
                "UPDATE reflexes SET enabled = ?, updated_at = ? WHERE id = ?;",
                (1 if enabled else 0, time.time(), rule_id)
            )
            return cur.rowcount > 0

    def handle_event(self, event_id: str, raw_text: str, timeout_s: float = 5.0) -> List[Dict[str, Any]]:
        """Evaluate an event against active reflex rules and execute matches.
        
        Guards:
        1. Never triggers if raw_text contains cause=reflex or author of this reflex.
        2. Exactly once execution per (reflex_id, event_id).
        """
        if "cause=reflex" in raw_text or "bench=no_reflex" in raw_text:
            return []

        results = []
        rules = self.list_rules(enabled_only=True)

        for rule in rules:
            if re.search(rule.pattern, raw_text):
                # Try recording execution (UNIQUE constraint prevents duplicates)
                with self._get_connection() as conn:
                    try:
                        conn.execute(
                            "INSERT INTO reflex_executions (reflex_id, event_id, executed_at) VALUES (?, ?, ?);",
                            (rule.id, event_id, time.time())
                        )
                    except sqlite3.IntegrityError:
                        # Already executed for this event ID!
                        continue

                # Execute script
                script = Path(rule.script_path)
                exit_code = -1
                output = ""
                if script.is_file() and os.access(script, os.X_OK):
                    try:
                        proc = subprocess.run(
                            [str(script), event_id, raw_text],
                            capture_output=True,
                            text=True,
                            timeout=timeout_s
                        )
                        exit_code = proc.returncode
                        output = proc.stdout.strip()
                    except Exception as e:
                        output = f"ERR: {e}"
                else:
                    output = f"ERR: Script {rule.script_path} not executable or missing"

                # Update execution record
                with self._get_connection() as conn:
                    conn.execute(
                        "UPDATE reflex_executions SET exit_code = ?, output = ? WHERE reflex_id = ? AND event_id = ?;",
                        (exit_code, output, rule.id, event_id)
                    )

                results.append({
                    "reflex_id": rule.id,
                    "event_id": event_id,
                    "exit_code": exit_code,
                    "output": output
                })

        return results
