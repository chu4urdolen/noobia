#!/usr/bin/env python3
"""Bounded Nexus client for Argus's private historian over pinned SSH."""

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
from zoneinfo import ZoneInfo

from argus_forge_sync import sync


NOOBIA = Path(os.environ.get("NOOBIA", "/noobia"))
HISTORY = NOOBIA / "argus/tools/argus_history.py"
JOBS = NOOBIA / "argus/tools/argus_jobs.py"
JOB_ID = re.compile(r"[0-9a-f]{32}\Z")


def remote(tool, command, *arguments):
    if tool not in ("history", "jobs"):
        raise ValueError("invalid Argus tool")
    script = HISTORY if tool == "history" else JOBS
    remote_command = " ".join(shlex.quote(str(part)) for part in
                              ("python3", str(script), command, *arguments))
    argv = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
            "-o", "ConnectTimeout=5", "argus", remote_command]
    try:
        outcome = subprocess.run(argv, capture_output=True, text=True, timeout=20, check=False)
    except subprocess.TimeoutExpired as error:
        raise ValueError("Argus request timed out") from error
    if outcome.returncode:
        raise ValueError((outcome.stderr or outcome.stdout).strip()[:300] or
                         f"Argus exited {outcome.returncode}")
    try:
        return json.loads(outcome.stdout)
    except json.JSONDecodeError as error:
        raise ValueError("Argus returned invalid JSON") from error


def valid_date(value):
    if value is None:
        return datetime.now(ZoneInfo("Europe/Sofia")).date().isoformat()
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("date must be YYYY-MM-DD")
    datetime.strptime(value, "%Y-%m-%d")
    return value


def worker_service():
    command = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
               "-o", "ConnectTimeout=5", "argus", "systemctl", "show",
               "argus-historian-worker.service", "--no-pager", "--property=ActiveState",
               "--property=SubState", "--property=UnitFileState", "--property=NRestarts"]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
    except subprocess.TimeoutExpired as error:
        raise ValueError("Argus worker status timed out") from error
    if result.returncode:
        raise ValueError(result.stderr.strip()[:300] or "Argus worker status failed")
    return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)


def safe_filter(value, field):
    if value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > 200 or "\n" in value:
        raise ValueError(f"{field} must be 1..200 single-line characters")
    return value


def valid_offset(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 1_000_000:
        raise ValueError("offset must be 0..1000000")
    return value


def page(rows, offset):
    if not isinstance(rows, list):
        raise ValueError("Argus returned invalid page")
    return {"items": rows[:100], "next_offset": offset + 100 if len(rows) > 100 else None}


def call(action, *, date=None, job_id=None, query=None, project=None, actor=None,
         offset=0, kind=None, key=None, sha256=None):
    if action == "status":
        return {"history": remote("history", "status"), "jobs": remote("jobs", "health"),
                "worker": worker_service()}
    if action == "collect-day":
        date = valid_date(date)
        exported = sync("1970-01-01T00:00:00+00:00")
        archive = remote("jobs", "enqueue", "archive-import")
        ledger = remote("jobs", "enqueue", "ledger-day", "--date", date)
        return {"date": date, "forge": exported, "archive_job": archive,
                "job": ledger}
    if action == "ledger":
        return remote("history", "ledger", valid_date(date))
    if action == "events-on":
        offset = valid_offset(offset)
        return page(remote("history", "events-on", valid_date(date), "--limit", "101",
                           "--offset", str(offset)), offset)
    if action == "find-events":
        offset = valid_offset(offset)
        if query is None:
            raise ValueError("query is required")
        return page(remote("history", "find", safe_filter(query, "query"), "--limit", "101",
                           "--offset", str(offset)), offset)
    if action == "forge-notes-on":
        offset = valid_offset(offset)
        arguments = [valid_date(date), "--limit", "101", "--offset", str(offset)]
        if project is not None:
            arguments += ["--project", safe_filter(project, "project")]
        if actor is not None:
            arguments += ["--actor", safe_filter(actor, "actor")]
        return page(remote("history", "forge-notes-on", *arguments), offset)
    if action == "source-record":
        if kind not in ("archive", "forge"):
            raise ValueError("source kind must be archive or forge")
        if not isinstance(key, str) or not key or len(key) > 500:
            raise ValueError("invalid source key")
        if not isinstance(sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise ValueError("invalid source SHA-256")
        return remote("history", "source-record", kind, key, sha256)
    if action in ("job-status", "job-result"):
        if not isinstance(job_id, str) or not JOB_ID.fullmatch(job_id):
            raise ValueError("invalid job ID")
        return remote("jobs", action, job_id)
    raise ValueError("unknown Argus action")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("status")
    collect = actions.add_parser("collect-day")
    collect.add_argument("--date")
    ledger = actions.add_parser("ledger")
    ledger.add_argument("date")
    events = actions.add_parser("events-on")
    events.add_argument("date")
    events.add_argument("--offset", type=int, default=0)
    find = actions.add_parser("find-events")
    find.add_argument("query")
    find.add_argument("--offset", type=int, default=0)
    notes = actions.add_parser("forge-notes-on")
    notes.add_argument("date")
    notes.add_argument("--project")
    notes.add_argument("--actor")
    notes.add_argument("--offset", type=int, default=0)
    source = actions.add_parser("source-record")
    source.add_argument("kind", choices=("archive", "forge"))
    source.add_argument("key")
    source.add_argument("sha256")
    for name in ("job-status", "job-result"):
        item = actions.add_parser(name)
        item.add_argument("job_id")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(call(args.action, date=getattr(args, "date", None),
                              job_id=getattr(args, "job_id", None),
                              query=getattr(args, "query", None),
                              project=getattr(args, "project", None),
                              actor=getattr(args, "actor", None),
                              offset=getattr(args, "offset", 0),
                              kind=getattr(args, "kind", None),
                              key=getattr(args, "key", None),
                              sha256=getattr(args, "sha256", None)), ensure_ascii=False,
                         sort_keys=True))
        return 0
    except (OSError, ValueError) as error:
        print(f"argus-client: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
