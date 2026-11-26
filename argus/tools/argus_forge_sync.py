#!/usr/bin/env python3
"""Send Forge's public changes feed to Argus over pinned SSH, on demand."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from argus_forge_feed import MAX_FEED_BYTES, aware_utc, parse_feed


NOOBIA = Path(os.environ.get("NOOBIA", "/noobia"))
FORGE_DB = NOOBIA / "common/bin/forge-db"
REMOTE_HISTORY = NOOBIA / "argus/tools/argus_history.py"
DEFAULT_SINCE = "1970-01-01T00:00:00+00:00"


def sync(since):
    since_utc = aware_utc(since, "since")
    if since_utc is None:
        raise ValueError("since is required")
    try:
        exported = subprocess.run(
            [str(FORGE_DB), "--json", "changes", "--since", since_utc,
             "--include-archived"],
            capture_output=True, timeout=30, check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise ValueError("forge-db export timed out") from error
    if exported.returncode:
        detail = exported.stderr.decode("utf-8", errors="replace").strip()[:300]
        raise ValueError(f"forge-db export failed: {detail}")
    if len(exported.stdout) > MAX_FEED_BYTES:
        raise ValueError("Forge export exceeds 5 MiB limit")
    digest, records = parse_feed(exported.stdout)
    command = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
               "-o", "ConnectTimeout=5", "argus", "python3", str(REMOTE_HISTORY),
               "capture-forge", "--since", since_utc]
    try:
        delivered = subprocess.run(command, input=exported.stdout, capture_output=True,
                                   timeout=30, check=False)
    except subprocess.TimeoutExpired as error:
        raise ValueError("Argus Forge import timed out") from error
    if delivered.returncode:
        detail = delivered.stderr.decode("utf-8", errors="replace").strip()[:300]
        raise ValueError(f"Argus Forge import failed: {detail}")
    try:
        result = json.loads(delivered.stdout)
    except json.JSONDecodeError as error:
        raise ValueError("Argus returned invalid JSON") from error
    if result.get("sha256") != digest:
        raise ValueError("Argus Forge export hash mismatch")
    result["rows_validated"] = len(records)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", default=DEFAULT_SINCE)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(sync(args.since), ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, ValueError) as error:
        print(f"argus-forge-sync: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
