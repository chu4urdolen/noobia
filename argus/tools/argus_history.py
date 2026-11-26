#!/usr/bin/env python3
"""Argus's append-only local evidence index for his existing event archive."""

import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from argus_forge_feed import MAX_FEED_BYTES, aware_utc, parse_feed


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
CREATE TABLE IF NOT EXISTS forge_exports (
    export_id INTEGER PRIMARY KEY,
    sha256 TEXT NOT NULL UNIQUE,
    since_utc TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    raw_bytes BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS forge_records (
    stable_key TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    kind TEXT NOT NULL,
    source_id TEXT NOT NULL,
    occurred_at TEXT,
    observed_at TEXT,
    project TEXT,
    actor TEXT,
    raw_json TEXT NOT NULL,
    first_export_id INTEGER NOT NULL REFERENCES forge_exports(export_id),
    PRIMARY KEY(stable_key,content_sha256)
);
CREATE INDEX IF NOT EXISTS forge_records_time_idx ON forge_records(kind,occurred_at);
CREATE TABLE IF NOT EXISTS forge_export_records (
    export_id INTEGER NOT NULL REFERENCES forge_exports(export_id),
    stable_key TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    PRIMARY KEY(export_id,stable_key),
    FOREIGN KEY(stable_key,content_sha256) REFERENCES forge_records(stable_key,content_sha256)
);
CREATE TABLE IF NOT EXISTS daily_ledgers (
    ledger_id INTEGER PRIMARY KEY,
    local_date TEXT NOT NULL,
    version INTEGER NOT NULL,
    source_digest TEXT NOT NULL,
    created_at TEXT NOT NULL,
    markdown TEXT NOT NULL,
    UNIQUE(local_date,version),
    UNIQUE(local_date,source_digest)
);
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


def capture_forge(connection, data, since):
    since_utc = aware_utc(since, "since")
    if since_utc is None:
        raise ValueError("since is required")
    digest, records = parse_feed(data)
    if connection.execute("SELECT 1 FROM forge_exports WHERE sha256=?", (digest,)).fetchone():
        return {"sha256": digest, "snapshot_added": 0, "records_added": 0}
    with connection:
        cursor = connection.execute(
            "INSERT INTO forge_exports(sha256,since_utc,captured_at,raw_bytes) VALUES(?,?,?,?)",
            (digest, since_utc, now_utc(), data),
        )
        export_id = cursor.lastrowid
        added = 0
        for record in records:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO forge_records(stable_key,content_sha256,kind,source_id,"
                "occurred_at,observed_at,project,actor,raw_json,first_export_id) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (record["stable_key"], record["content_sha256"], record["kind"],
                 record["source_id"], record["occurred_at"], record["observed_at"],
                 record["project"], record["actor"],
                 json.dumps(record["raw_record"], ensure_ascii=False, sort_keys=True),
                 export_id),
            )
            added += cursor.rowcount
            connection.execute(
                "INSERT INTO forge_export_records(export_id,stable_key,content_sha256) VALUES(?,?,?)",
                (export_id, record["stable_key"], record["content_sha256"]),
            )
    return {"sha256": digest, "snapshot_added": 1, "records_added": added,
            "rows_seen": len(records)}


def forge_notes_on(connection, date):
    day = datetime.strptime(date, "%Y-%m-%d").date()
    sofia = ZoneInfo("Europe/Sofia")
    start = datetime.combine(day, datetime.min.time(), sofia).astimezone(timezone.utc)
    end = datetime.combine(day + timedelta(days=1), datetime.min.time(), sofia).astimezone(timezone.utc)
    rows = connection.execute(
        "SELECT f.stable_key,f.content_sha256,f.occurred_at,f.project,f.actor,f.raw_json "
        "FROM forge_records f WHERE f.kind='note' AND f.occurred_at>=? AND f.occurred_at<? "
        "AND f.first_export_id=(SELECT MAX(f2.first_export_id) FROM forge_records f2 "
        "WHERE f2.stable_key=f.stable_key) ORDER BY f.occurred_at,f.stable_key",
        (start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")),
    ).fetchall()
    result = []
    for key, digest, occurred_at, project, actor, raw_json in rows:
        raw = json.loads(raw_json)
        result.append({
            "stable_key": key,
            "sha256": digest,
            "occurred_at": occurred_at,
            "local_time": datetime.fromisoformat(occurred_at).astimezone(sofia).strftime("%H:%M"),
            "project": project,
            "actor": actor,
            "text": str(raw.get("note", "")),
            "paths": raw.get("paths", []),
        })
    return result


def compact_line(value, limit=500):
    return " ".join(str(value).split())[:limit]


def build_ledger(connection, date):
    datetime.strptime(date, "%Y-%m-%d")
    archive = events_on(connection, date, 1_000_000_000)
    notes = forge_notes_on(connection, date)
    evidence = sorted([("archive", str(item["record_id"]), item["sha256"])
                       for item in archive] +
                      [("forge", item["stable_key"], item["sha256"])
                       for item in notes])
    source_digest = hashlib.sha256(json.dumps(evidence, separators=(",", ":")).encode()).hexdigest()
    existing = connection.execute(
        "SELECT version FROM daily_ledgers WHERE local_date=? AND source_digest=?",
        (date, source_digest),
    ).fetchone()
    if existing:
        return {"date": date, "version": existing[0], "reused": True,
                "archive_events": len(archive), "forge_notes": len(notes)}
    lines = [f"# Noobia evidence ledger — {date}", "", "Times are Europe/Sofia."
             " Source statements are recorded as evidence, not independently confirmed facts.", ""]
    lines.append("## Date-only archive events")
    for item in archive:
        lines.append(f"- **{compact_line(item['title'] or item['event_type'], 120)}**: "
                     f"{compact_line(item['summary'])} "
                     f"[Argus {item['event_id']}, {item['source_path']}:{item['source_line']}, "
                     f"sha256:{item['sha256']}]")
    if not archive:
        lines.append("- No explicitly dated Argus archive events captured.")
    lines.extend(("", "## Timed Forge notes"))
    for item in notes:
        lines.append(f"- **{item['local_time']} — {compact_line(item['actor'] or 'unknown', 60)} "
                     f"on {compact_line(item['project'] or 'unspecified', 80)}**: "
                     f"{compact_line(item['text'])} "
                     f"[Forge {item['stable_key']}, sha256:{item['sha256']}]")
    if not notes:
        lines.append("- No Forge notes captured for this local day.")
    markdown = "\n".join(lines) + "\n"
    if len(markdown.encode("utf-8")) > 5 * 1024 * 1024:
        raise ValueError("ledger exceeds 5 MiB")
    with connection:
        next_version = connection.execute(
            "SELECT COALESCE(MAX(version),0)+1 FROM daily_ledgers WHERE local_date=?", (date,)
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO daily_ledgers(local_date,version,source_digest,created_at,markdown) "
            "VALUES(?,?,?,?,?)", (date, next_version, source_digest, now_utc(), markdown),
        )
    return {"date": date, "version": next_version, "reused": False,
            "archive_events": len(archive), "forge_notes": len(notes)}


def ledger_on(connection, date):
    datetime.strptime(date, "%Y-%m-%d")
    row = connection.execute(
        "SELECT version,source_digest,created_at,markdown FROM daily_ledgers "
        "WHERE local_date=? ORDER BY version DESC LIMIT 1", (date,)
    ).fetchone()
    if row is None:
        raise ValueError(f"no ledger for {date}")
    return {"date": date, "version": row[0], "source_digest": row[1],
            "created_at": row[2], "markdown": row[3]}


def status(connection):
    captures = [value for value in (
        connection.execute("SELECT MAX(captured_at) FROM file_snapshots").fetchone()[0],
        connection.execute("SELECT MAX(captured_at) FROM forge_exports").fetchone()[0],
    ) if value is not None]
    return {
        "snapshots": connection.execute("SELECT COUNT(*) FROM file_snapshots").fetchone()[0],
        "raw_records": connection.execute("SELECT COUNT(*) FROM raw_records").fetchone()[0],
        "events": connection.execute("SELECT COUNT(*) FROM events").fetchone()[0],
        "forge_exports": connection.execute("SELECT COUNT(*) FROM forge_exports").fetchone()[0],
        "forge_records": connection.execute("SELECT COUNT(*) FROM forge_records").fetchone()[0],
        "ledgers": connection.execute("SELECT COUNT(*) FROM daily_ledgers").fetchone()[0],
        "last_capture_utc": max(captures, default=None),
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
    forge = sub.add_parser("capture-forge")
    forge.add_argument("--since", default="1970-01-01T00:00:00+00:00")
    build = sub.add_parser("build-ledger")
    build.add_argument("date")
    ledger = sub.add_parser("ledger")
    ledger.add_argument("date")
    sub.add_parser("status")
    args = parser.parse_args(argv)
    try:
        if args.command in ("events-on", "find") and not 1 <= args.limit <= 1000:
            raise ValueError("limit must be 1..1000")
        with closing(connect(args.db)) as connection, connection:
            if args.command == "init":
                result = {"db": str(args.db), "schema": 2}
            elif args.command == "import-archive":
                result = import_archive(connection, args.archive_root)
            elif args.command == "events-on":
                result = events_on(connection, args.date, args.limit)
            elif args.command == "find":
                result = find_events(connection, args.query, args.limit)
            elif args.command == "capture-forge":
                result = capture_forge(connection, sys.stdin.buffer.read(MAX_FEED_BYTES + 1), args.since)
            elif args.command == "build-ledger":
                result = build_ledger(connection, args.date)
            elif args.command == "ledger":
                result = ledger_on(connection, args.date)
            else:
                result = status(connection)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, sqlite3.Error, ValueError) as error:
        print(f"argus-history: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
