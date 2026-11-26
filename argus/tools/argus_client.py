#!/usr/bin/env python3
"""Bounded Nexus client for Argus's private historian over pinned SSH."""

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
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
    argv = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
            "-o", "ConnectTimeout=5", "argus", "python3", str(script), command,
            *arguments]
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


def call(action, *, date=None, job_id=None):
    if action == "status":
        return {"history": remote("history", "status"), "jobs": remote("jobs", "health")}
    if action == "collect-day":
        date = valid_date(date)
        exported = sync("1970-01-01T00:00:00+00:00")
        archive = remote("jobs", "enqueue", "archive-import")
        ledger = remote("jobs", "enqueue", "ledger-day", "--date", date)
        return {"date": date, "forge": exported, "archive_job": archive,
                "job": ledger}
    if action == "ledger":
        return remote("history", "ledger", valid_date(date))
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
    for name in ("job-status", "job-result"):
        item = actions.add_parser(name)
        item.add_argument("job_id")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(call(args.action, date=getattr(args, "date", None),
                              job_id=getattr(args, "job_id", None)), ensure_ascii=False,
                         sort_keys=True))
        return 0
    except (OSError, ValueError) as error:
        print(f"argus-client: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
