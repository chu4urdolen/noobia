#!/usr/bin/env python3
"""Argus's append-only local evidence index for his existing event archive."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from datetime import datetime, timezone


NOOBIA = Path(os.environ.get("NOOBIA", "/noobia"))
DEFAULT_DB = NOOBIA / "argus/data/history.sqlite3"
DEFAULT_ARCHIVE = NOOBIA / "archive"

SCHEMA = """
CREATE TABLE IF NOT EXISTS file_snapshots (
    snapshot_id INTEGER PRIMARY KEY,
    source_path TEXT NOT NULL,
    file_sha256 TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    byte_count INTEGER NOT NULL,
    raw_bytes BLOB NOT NULL,
    UNIQUE(source_path, file_sha256)
);
CREATE TABLE IF NOT EXISTS raw_records (
    record_id INTEGER PRIMARY KEY,
    source_path TEXT NOT NULL,
    line_sha256 TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    first_snapshot_id INTEGER NOT NULL REFERENCES file_snapshots(snapshot_id),
    first_line INTEGER NOT NULL,
    UNIQUE(source_path, line_sha256)
);
CREATE TABLE IF NOT EXISTS snapshot_records (
    snapshot_id INTEGER NOT NULL REFERENCES file_snapshots(snapshot_id),
    line_number INTEGER NOT NULL,
    record_id INTEGER NOT NULL REFERENCES raw_records(record_id),
    PRIMARY KEY(snapshot_id, line_number)
);
CREATE TABLE IF NOT EXISTS events (
    record_id INTEGER PRIMARY KEY REFERENCES raw_records(record_id),
    event_id TEXT NOT NULL,
    event_date TEXT,
    recorded_at TEXT NOT NULL,
    event_type TEXT NOT NULL,
    title TEXT,
    summary TEXT NOT NULL,
    participants_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_date_idx ON events(event_date, event_id);
CREATE INDEX IF NOT EXISTS events_id_idx ON events(event_id);
"""


def now_utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(db_path):
    if db_path.is_symlink():
        raise ValueError(f"database path is a symlink: {db_path}")
    db_path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    if not db_path.exists():
        descriptor = os.open(db_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
    connection = sqlite3.connect(db_path)
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA journal_mode=WAL")
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version not in (0, 1):
        connection.close()
        raise ValueError(f"unsupported history schema version: {version}")
    connection.executescript(SCHEMA)
    if version == 0:
        connection.execute("PRAGMA user_version=1")
    return connection


def parse_record(line, path, line_number):
    try:
        item = json.loads(line)
        if not isinstance(item, dict):
            raise ValueError("expected a JSON object")
        for key in ("event_id", "recorded_at", "type", "summary"):
            if not isinstance(item.get(key), str) or not item[key]:
                raise ValueError(f"missing or invalid {key}")
        date = item.get("event_date")
        if date is not None:
            if not isinstance(date, str) or not date:
                raise ValueError("invalid event_date")
            # A year or month is valid historical precision; do not invent a day.
            if not re.fullmatch(r"\d{4}(?:-\d{2}(?:-\d{2})?)?", date):
                raise ValueError("invalid event_date precision")
            if len(date) == 10:
                datetime.strptime(date, "%Y-%m-%d")
        participants = item.get("participants", [])
        if not isinstance(participants, list):
            raise ValueError("invalid participants")
        return item
    except (json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{path}:{line_number}: {error}") from error


def import_file(connection, path, archive_root):
    source_path = str(path.relative_to(archive_root))
    data = path.read_bytes()
    file_hash = hashlib.sha256(data).hexdigest()
    if connection.execute(
        "SELECT 1 FROM file_snapshots WHERE source_path=? AND file_sha256=?",
        (source_path, file_hash),
    ).fetchone():
        return 0, 0
    lines = data.splitlines(keepends=True)
    parsed = []
    for number, raw_line in enumerate(lines, 1):
        if not raw_line.strip():
            continue
        try:
            line = raw_line.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError(f"{source_path}:{number}: invalid UTF-8") from error
        parsed.append((number, line, hashlib.sha256(raw_line).hexdigest(),
                       parse_record(line, source_path, number)))
    captured_at = now_utc()
    with connection:
        cursor = connection.execute(
            "INSERT INTO file_snapshots(source_path,file_sha256,captured_at,byte_count,raw_bytes) VALUES(?,?,?,?,?)",
            (source_path, file_hash, captured_at, len(data), data),
        )
        snapshot_id = cursor.lastrowid
        new_records = 0
        for number, line, line_hash, item in parsed:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO raw_records(source_path,line_sha256,raw_json,first_snapshot_id,first_line) "
                "VALUES(?,?,?,?,?)",
                (source_path, line_hash, line, snapshot_id, number),
            )
            new_records += cursor.rowcount
            record_id = connection.execute(
                "SELECT record_id FROM raw_records WHERE source_path=? AND line_sha256=?",
                (source_path, line_hash),
            ).fetchone()[0]
            connection.execute(
                "INSERT INTO snapshot_records(snapshot_id,line_number,record_id) VALUES(?,?,?)",
                (snapshot_id, number, record_id),
            )
            connection.execute(
                "INSERT OR IGNORE INTO events(record_id,event_id,event_date,recorded_at,event_type,title,summary,participants_json) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (record_id, item["event_id"], item.get("event_date"), item["recorded_at"],
                 item["type"], item.get("title"), item["summary"],
                 json.dumps(item.get("participants", []), ensure_ascii=False)),
            )
    return 1, new_records


def import_archive(connection, archive_root):
    archive_root = archive_root.resolve()
    events_dir = archive_root / "events"
    if not events_dir.is_dir():
        raise ValueError(f"archive events directory missing: {events_dir}")
    files = sorted(events_dir.glob("*/*.jsonl"))
    snapshots = records = 0
    for path in files:
        if not path.is_file() or not path.resolve().is_relative_to(events_dir.resolve()):
            raise ValueError(f"unsafe archive path: {path}")
        added_snapshots, added_records = import_file(connection, path, archive_root)
        snapshots += added_snapshots
        records += added_records
    return {"files_seen": len(files), "snapshots_added": snapshots, "records_added": records}


def events_on(connection, date, limit):
    datetime.strptime(date, "%Y-%m-%d")
    rows = connection.execute(
        "SELECT e.event_id,e.event_date,e.recorded_at,e.event_type,e.title,e.summary,"
        "e.participants_json,r.record_id,r.source_path,r.first_line,r.line_sha256 "
        "FROM events e JOIN raw_records r USING(record_id) WHERE e.event_date=? "
        "ORDER BY e.event_id,r.record_id LIMIT ?",
        (date, limit),
    ).fetchall()
    return [dict(event_id=row[0], event_date=row[1], recorded_at=row[2],
                 event_type=row[3], title=row[4], summary=row[5],
                 participants=json.loads(row[6]), record_id=row[7],
                 source_path=row[8], source_line=row[9], sha256=row[10]) for row in rows]


def find_events(connection, query, limit):
    if not query.strip():
        raise ValueError("query must not be empty")
    needle = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    rows = connection.execute(
        "SELECT e.event_id,e.event_date,e.recorded_at,e.event_type,e.title,e.summary,"
        "e.participants_json,r.record_id,r.source_path,r.first_line,r.line_sha256 "
        "FROM events e JOIN raw_records r USING(record_id) "
        "WHERE e.event_id LIKE ? ESCAPE '\\' OR e.title LIKE ? ESCAPE '\\' "
        "OR e.summary LIKE ? ESCAPE '\\' OR e.participants_json LIKE ? ESCAPE '\\' "
        "ORDER BY e.event_date,e.event_id,r.record_id LIMIT ?",
        (needle, needle, needle, needle, limit),
    ).fetchall()
    return [dict(event_id=row[0], event_date=row[1], recorded_at=row[2],
                 event_type=row[3], title=row[4], summary=row[5],
                 participants=json.loads(row[6]), record_id=row[7],
                 source_path=row[8], source_line=row[9], sha256=row[10]) for row in rows]


def status(connection):
    return {
        "snapshots": connection.execute("SELECT COUNT(*) FROM file_snapshots").fetchone()[0],
        "raw_records": connection.execute("SELECT COUNT(*) FROM raw_records").fetchone()[0],
        "events": connection.execute("SELECT COUNT(*) FROM events").fetchone()[0],
        "last_capture_utc": connection.execute("SELECT MAX(captured_at) FROM file_snapshots").fetchone()[0],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    importer = sub.add_parser("import-archive")
    importer.add_argument("--archive-root", type=Path, default=DEFAULT_ARCHIVE)
    query = sub.add_parser("events-on")
    query.add_argument("date")
    query.add_argument("--limit", type=int, default=100)
    search = sub.add_parser("find")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=100)
    sub.add_parser("status")
    args = parser.parse_args(argv)
    try:
        if args.command in ("events-on", "find") and not 1 <= args.limit <= 1000:
            raise ValueError("limit must be 1..1000")
        with connect(args.db) as connection:
            if args.command == "init":
                result = {"db": str(args.db), "schema": 1}
            elif args.command == "import-archive":
                result = import_archive(connection, args.archive_root)
            elif args.command == "events-on":
                result = events_on(connection, args.date, args.limit)
            elif args.command == "find":
                result = find_events(connection, args.query, args.limit)
            else:
                result = status(connection)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, sqlite3.Error, ValueError) as error:
        print(f"argus-history: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
