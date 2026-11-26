#!/usr/bin/env python3
"""Private durable queue for bounded, named Argus historian jobs."""

import argparse
from contextlib import closing, contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import sqlite3
import stat
import subprocess
import sys
import time
import uuid


NOOBIA = Path(os.environ.get("NOOBIA", "/noobia"))
DEFAULT_DB = NOOBIA / "argus/data/jobs.sqlite3"
HISTORY_TOOL = NOOBIA / "argus/tools/argus_history.py"
KINDS = ("archive-import", "ledger-day")
JOB_ID = re.compile(r"[0-9a-f]{32}\Z")
SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    target_date TEXT,
    request_key TEXT UNIQUE,
    state TEXT NOT NULL CHECK(state IN ('queued','running','done','failed')),
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    result_json TEXT,
    error TEXT
);
CREATE INDEX IF NOT EXISTS jobs_state_idx ON jobs(state, created_at, job_id);
"""


def now_utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path):
    if path.is_symlink():
        raise ValueError(f"job database path is a symlink: {path}")
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    if not path.exists():
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
    connection = sqlite3.connect(path, timeout=10)
    connection.execute("PRAGMA journal_mode=WAL")
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version not in (0, 1, 2):
        connection.close()
        raise ValueError(f"unsupported job schema version: {version}")
    connection.executescript(SCHEMA)
    if version == 1:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(jobs)")}
        if "target_date" not in columns:
            connection.execute("ALTER TABLE jobs ADD COLUMN target_date TEXT")
    if version < 2:
        connection.execute("PRAGMA user_version=2")
        connection.commit()
    return connection


@contextmanager
def worker_lock(db_path):
    lock_path = db_path.with_suffix(".lock")
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("invalid worker lock file")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("another Argus worker is active") from error
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def enqueue(connection, kind, request_key=None, target_date=None):
    if kind not in KINDS:
        raise ValueError(f"unsupported job kind: {kind}")
    if request_key is not None and (not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", request_key)):
        raise ValueError("request key must be 1..128 safe characters")
    if kind == "ledger-day":
        if not isinstance(target_date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", target_date):
            raise ValueError("ledger-day requires --date YYYY-MM-DD")
        datetime.strptime(target_date, "%Y-%m-%d")
    elif target_date is not None:
        raise ValueError("archive-import does not accept a date")
    with connection:
        connection.execute("BEGIN IMMEDIATE")
        if request_key:
            existing = connection.execute(
                "SELECT job_id,state FROM jobs WHERE request_key=?", (request_key,)
            ).fetchone()
            if existing:
                return {"job_id": existing[0], "state": existing[1], "reused": True}
        job_id = uuid.uuid4().hex
        connection.execute(
            "INSERT INTO jobs(job_id,kind,target_date,request_key,state,created_at) "
            "VALUES(?,?,?,?,'queued',?)",
            (job_id, kind, target_date, request_key, now_utc()),
        )
    return {"job_id": job_id, "state": "queued", "reused": False}


def claim_next(connection):
    with connection:
        connection.execute("BEGIN IMMEDIATE")
        if connection.execute("SELECT 1 FROM jobs WHERE state='running' LIMIT 1").fetchone():
            return None
        row = connection.execute(
            "SELECT job_id,kind,target_date FROM jobs WHERE state='queued' "
            "ORDER BY rowid LIMIT 1"
        ).fetchone()
        if row:
            connection.execute(
                "UPDATE jobs SET state='running',started_at=? WHERE job_id=? AND state='queued'",
                (now_utc(), row[0]),
            )
    return row


def recover_interrupted(connection):
    with connection:
        cursor = connection.execute(
            "UPDATE jobs SET state='failed',finished_at=?,error=? WHERE state='running'",
            (now_utc(), "worker interrupted; retry requires a new request key"),
        )
    return cursor.rowcount


def finish(connection, job_id, result=None, error=None):
    if not JOB_ID.fullmatch(job_id):
        raise ValueError("invalid job ID")
    if (result is None) == (error is None):
        raise ValueError("exactly one of result or error is required")
    if result is not None:
        serialized = json.dumps(result, ensure_ascii=False, sort_keys=True)
        if len(serialized.encode("utf-8")) > 8192:
            raise ValueError("job result exceeds 8 KiB")
    else:
        serialized = None
        error = str(error)[:500]
    with connection:
        cursor = connection.execute(
            "UPDATE jobs SET state=?,result_json=?,error=?,finished_at=? "
            "WHERE job_id=? AND state='running'",
            ("done" if error is None else "failed", serialized, error, now_utc(), job_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("job is not running")


def dispatch(kind, target_date):
    if kind == "archive-import" and target_date is None:
        action = ["import-archive"]
    elif kind == "ledger-day" and target_date is not None:
        action = ["build-ledger", target_date]
    else:
        raise ValueError(f"unsupported job kind: {kind}")
    command = [sys.executable, str(HISTORY_TOOL), *action]
    try:
        completed = subprocess.run(command, capture_output=True, text=True,
                                   timeout=120, check=False)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"{kind} exceeded 120 seconds") from error
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip()[:500] or f"{kind} failed")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"{kind} returned invalid JSON") from error


def run_once(connection, dispatcher=dispatch):
    job = claim_next(connection)
    if job is None:
        return {"claimed": False}
    job_id, kind, target_date = job
    try:
        result = dispatcher(kind, target_date)
        finish(connection, job_id, result=result)
        return {"claimed": True, "job_id": job_id, "state": "done", "result": result}
    except Exception as error:
        finish(connection, job_id, error=str(error))
        return {"claimed": True, "job_id": job_id, "state": "failed", "error": str(error)[:500]}


def job_status(connection, job_id, include_result=False):
    if not JOB_ID.fullmatch(job_id):
        raise ValueError("invalid job ID")
    row = connection.execute(
        "SELECT job_id,kind,target_date,state,created_at,started_at,finished_at,result_json,error "
        "FROM jobs WHERE job_id=?", (job_id,)
    ).fetchone()
    if row is None:
        raise ValueError("job not found")
    result = dict(zip(("job_id", "kind", "target_date", "state", "created_at",
                       "started_at", "finished_at"), row[:7]))
    if include_result:
        result["result"] = json.loads(row[7]) if row[7] is not None else None
        result["error"] = row[8]
    return result


def health(connection):
    counts = {state: 0 for state in ("queued", "running", "done", "failed")}
    counts.update(connection.execute(
        "SELECT state,COUNT(*) FROM jobs GROUP BY state"
    ).fetchall())
    return counts


def worker(connection):
    interrupted = recover_interrupted(connection)
    print(json.dumps({"worker": "started", "interrupted_jobs": interrupted}), flush=True)
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while not stopping:
        outcome = run_once(connection)
        if outcome["claimed"]:
            print(json.dumps(outcome, ensure_ascii=False, sort_keys=True), flush=True)
        else:
            time.sleep(2)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    add = commands.add_parser("enqueue")
    add.add_argument("kind", choices=KINDS)
    add.add_argument("--request-key")
    add.add_argument("--date")
    commands.add_parser("run-once")
    for name in ("job-status", "job-result"):
        command = commands.add_parser(name)
        command.add_argument("job_id")
    commands.add_parser("health")
    commands.add_parser("worker")
    args = parser.parse_args(argv)
    try:
        with closing(connect(args.db)) as connection:
            if args.command == "init":
                output = {"db": str(args.db), "schema": 2}
            elif args.command == "enqueue":
                output = enqueue(connection, args.kind, args.request_key, args.date)
            elif args.command == "run-once":
                with worker_lock(args.db):
                    recover_interrupted(connection)
                    output = run_once(connection)
            elif args.command == "job-status":
                output = job_status(connection, args.job_id)
            elif args.command == "job-result":
                output = job_status(connection, args.job_id, include_result=True)
            elif args.command == "health":
                output = health(connection)
            else:
                with worker_lock(args.db):
                    worker(connection)
                return 0
        print(json.dumps(output, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, sqlite3.Error, ValueError, RuntimeError) as error:
        print(f"argus-jobs: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
