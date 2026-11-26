#!/usr/bin/env python3
"""Argus's append-only evidence index for events and registered journals."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone


NOOBIA = Path(os.environ.get("NOOBIA", "/noobia"))
DEFAULT_DB = NOOBIA / "argus/data/history.sqlite3"
DEFAULT_ARCHIVE = NOOBIA / "archive"
JOURNAL_SOURCES = {
    "aria": ("Aria", str(NOOBIA / "aria/JOURNAL.md")),
    "dushich": ("Dushich", str(NOOBIA / "dushich/JOURNAL.md")),
    "gwyn": ("Gwyn App Nub", str(NOOBIA / "gwyn-app-nub/JOURNAL.md")),
}
MAX_JOURNAL_BYTES = 5 * 1024 * 1024

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
CREATE TABLE IF NOT EXISTS journal_snapshots (
    snapshot_id INTEGER PRIMARY KEY,
    source_id TEXT NOT NULL,
    source_owner TEXT NOT NULL,
    source_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    raw_bytes BLOB NOT NULL,
    UNIQUE(source_id, sha256)
);
CREATE TABLE IF NOT EXISTS journal_sections (
    snapshot_id INTEGER NOT NULL REFERENCES journal_snapshots(snapshot_id),
    line_number INTEGER NOT NULL,
    event_date TEXT NOT NULL,
    heading TEXT NOT NULL,
    excerpt TEXT NOT NULL,
    PRIMARY KEY(snapshot_id, line_number)
);
CREATE INDEX IF NOT EXISTS journal_sections_date_idx ON journal_sections(event_date, snapshot_id);
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
    if version not in (0, 1, 2):
        connection.close()
        raise ValueError(f"unsupported history schema version: {version}")
    connection.executescript(SCHEMA)
    if version < 2:
        connection.execute("PRAGMA user_version=2")
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


def journal_sections(data):
    try:
        lines = data.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise ValueError("journal is not UTF-8") from error
    sections = []
    for number, line in enumerate(lines, 1):
        match = re.match(r"^## (\d{4}-\d{2}-\d{2})(?:\b|$)", line)
        if not match:
            continue
        date = match.group(1)
        datetime.strptime(date, "%Y-%m-%d")
        excerpt = ""
        for following in lines[number:]:
            if following.startswith("## "):
                break
            stripped = following.strip()
            if stripped and not stripped.startswith("#"):
                excerpt = stripped[:240]
                break
        sections.append((number, date, line[3:].strip(), excerpt))
    return sections


def capture_journal(connection, source_id, data):
    if source_id not in JOURNAL_SOURCES:
        raise ValueError(f"unregistered journal source: {source_id}")
    if len(data) > MAX_JOURNAL_BYTES:
        raise ValueError("journal exceeds 5 MiB limit")
    digest = hashlib.sha256(data).hexdigest()
    if connection.execute(
        "SELECT 1 FROM journal_snapshots WHERE source_id=? AND sha256=?",
        (source_id, digest),
    ).fetchone():
        return {"source": source_id, "sha256": digest, "snapshot_added": 0}
    sections = journal_sections(data)
    owner, path = JOURNAL_SOURCES[source_id]
    with connection:
        cursor = connection.execute(
            "INSERT INTO journal_snapshots(source_id,source_owner,source_path,sha256,captured_at,raw_bytes) "
            "VALUES(?,?,?,?,?,?)",
            (source_id, owner, path, digest, now_utc(), data),
        )
        snapshot_id = cursor.lastrowid
        connection.executemany(
            "INSERT INTO journal_sections(snapshot_id,line_number,event_date,heading,excerpt) VALUES(?,?,?,?,?)",
            [(snapshot_id, *section) for section in sections],
        )
    return {"source": source_id, "sha256": digest, "snapshot_added": 1,
            "dated_sections": len(sections)}


def journal_day(connection, date, limit):
    datetime.strptime(date, "%Y-%m-%d")
    rows = connection.execute(
        "SELECT j.source_id,j.source_owner,j.source_path,j.sha256,j.captured_at,"
        "s.line_number,s.heading,s.excerpt FROM journal_sections s "
        "JOIN journal_snapshots j USING(snapshot_id) "
        "WHERE s.event_date=? AND j.snapshot_id=("
        "SELECT MAX(j2.snapshot_id) FROM journal_snapshots j2 WHERE j2.source_id=j.source_id) "
        "ORDER BY j.source_id,s.line_number LIMIT ?",
        (date, limit),
    ).fetchall()
    return [dict(source=row[0], owner=row[1], source_path=row[2],
                 snapshot_sha256=row[3], captured_at=row[4], source_line=row[5],
                 heading=row[6], excerpt=row[7]) for row in rows]


def sync_journals():
    """Push registered Nexus journals over the pinned Argus SSH route."""
    results = []
    for source_id, (_, source_path) in JOURNAL_SOURCES.items():
        path = Path(source_path)
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"registered journal missing or symlinked: {path}")
        before = path.stat()
        if before.st_size > MAX_JOURNAL_BYTES:
            raise ValueError(f"registered journal exceeds 5 MiB: {path}")
        data = path.read_bytes()
        after = path.stat()
        if (before.st_mtime_ns, before.st_size) != (after.st_mtime_ns, after.st_size):
            raise ValueError(f"registered journal changed during read: {path}")
        if len(data) > MAX_JOURNAL_BYTES:
            raise ValueError(f"registered journal exceeds 5 MiB: {path}")
        expected_hash = hashlib.sha256(data).hexdigest()
        command = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
                   "-o", "ConnectTimeout=4", "argus", "python3",
                   str(NOOBIA / "argus/tools/argus_history.py"), "capture-journal", source_id]
        try:
            completed = subprocess.run(command, input=data, capture_output=True, timeout=15,
                                       check=False)
        except subprocess.TimeoutExpired as error:
            raise ValueError(f"Argus capture timed out for {source_id}") from error
        if completed.returncode:
            detail = completed.stderr.decode("utf-8", errors="replace").strip()[:300]
            raise ValueError(f"Argus capture failed for {source_id}: {detail}")
        try:
            result = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise ValueError(f"Argus returned invalid JSON for {source_id}") from error
        if result.get("source") != source_id or result.get("sha256") != expected_hash:
            raise ValueError(f"Argus capture hash mismatch for {source_id}")
        results.append(result)
    return results


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
    latest_archive = connection.execute("SELECT MAX(captured_at) FROM file_snapshots").fetchone()[0]
    latest_journal = connection.execute("SELECT MAX(captured_at) FROM journal_snapshots").fetchone()[0]
    return {
        "snapshots": connection.execute("SELECT COUNT(*) FROM file_snapshots").fetchone()[0],
        "raw_records": connection.execute("SELECT COUNT(*) FROM raw_records").fetchone()[0],
        "events": connection.execute("SELECT COUNT(*) FROM events").fetchone()[0],
        "journal_snapshots": connection.execute("SELECT COUNT(*) FROM journal_snapshots").fetchone()[0],
        "journal_sources": connection.execute("SELECT COUNT(DISTINCT source_id) FROM journal_snapshots").fetchone()[0],
        "last_capture_utc": max((value for value in (latest_archive, latest_journal)
                                 if value is not None), default=None),
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
    capture = sub.add_parser("capture-journal")
    capture.add_argument("source", choices=sorted(JOURNAL_SOURCES))
    day = sub.add_parser("journal-day")
    day.add_argument("date")
    day.add_argument("--limit", type=int, default=100)
    sub.add_parser("sync-journals")
    sub.add_parser("status")
    args = parser.parse_args(argv)
    try:
        if args.command in ("events-on", "find", "journal-day") and not 1 <= args.limit <= 1000:
            raise ValueError("limit must be 1..1000")
        if args.command == "sync-journals":
            print(json.dumps(sync_journals(), ensure_ascii=False, sort_keys=True))
            return 0
        with connect(args.db) as connection:
            if args.command == "init":
                result = {"db": str(args.db), "schema": 1}
            elif args.command == "import-archive":
                result = import_archive(connection, args.archive_root)
            elif args.command == "events-on":
                result = events_on(connection, args.date, args.limit)
            elif args.command == "find":
                result = find_events(connection, args.query, args.limit)
            elif args.command == "capture-journal":
                result = capture_journal(connection, args.source,
                                         sys.stdin.buffer.read(MAX_JOURNAL_BYTES + 1))
            elif args.command == "journal-day":
                result = journal_day(connection, args.date, args.limit)
            else:
                result = status(connection)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, sqlite3.Error, ValueError) as error:
        print(f"argus-history: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
