#!/usr/bin/env python3
"""Make and verify private, immutable Argus evidence backups on the Nexus."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tarfile
import tempfile


NOOBIA = Path(os.environ.get("NOOBIA", "/noobia"))
DESTINATION = NOOBIA / "argus/private/backups"
REMOTE = NOOBIA / "argus/tools/argus_backup_source.py"
FILES = {"history": "history.sqlite3", "jobs": "jobs.sqlite3",
         "archive": "archive.tar"}


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def check_snapshot(folder):
    manifest = json.loads((folder / "manifest.json").read_text())
    if set(manifest["files"]) != set(FILES.values()):
        raise ValueError("backup manifest file set is incomplete")
    for name, expected in manifest["files"].items():
        path = folder / name
        if not path.is_file() or path.is_symlink() or digest(path) != expected["sha256"]:
            raise ValueError(f"backup hash mismatch: {name}")
    integrity = {}
    for name in ("history", "jobs"):
        path = folder / FILES[name]
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
            result = db.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise ValueError(f"{name} SQLite integrity check: {result}")
        integrity[name] = result
    with tarfile.open(folder / FILES["archive"], "r:") as tar:
        members = tar.getmembers()
        if not members or any((m.name != "archive" and not m.name.startswith("archive/")) or
                              ".." in Path(m.name).parts or m.issym() or m.islnk()
                              for m in members):
            raise ValueError("unsafe archive backup members")
        event_members = [m for m in members if m.isfile() and
                         m.name.startswith("archive/events/") and m.name.endswith(".jsonl")]
        archive_events = len(event_members)
        if archive_events:
            sys.path.insert(0, str(NOOBIA / "argus/tools"))
            from argus_history import connect, import_archive
            with tempfile.TemporaryDirectory(prefix="argus-restore-") as temporary:
                root = Path(temporary)
                for member in event_members:
                    target = root / member.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with tar.extractfile(member) as source, target.open("wb") as output:
                        while chunk := source.read(1024 * 1024):
                            output.write(chunk)
                with connect(root / "restored.sqlite3") as db:
                    restored = import_archive(db, root / "archive")
                if restored["files_seen"] != archive_events:
                    raise ValueError("archive restore count mismatch")
    if archive_events == 0:
        raise ValueError("archive backup contains no event files")
    return {"backup": str(folder), "sqlite_integrity": integrity,
            "archive_event_files": archive_events,
            "restored_archive_records": restored["records_added"],
            "sha256": {name: info["sha256"] for name, info in manifest["files"].items()}}


def make_backup():
    DESTINATION.mkdir(parents=True, mode=0o700, exist_ok=True)
    os.chmod(DESTINATION, 0o700)
    with tempfile.TemporaryDirectory(prefix=".incomplete-", dir=DESTINATION) as temporary:
        staging = Path(temporary)
        files = {}
        for source, name in FILES.items():
            path = staging / name
            with path.open("wb") as output:
                os.chmod(path, 0o600)
                command = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
                           "-o", "ConnectTimeout=5", "argus", "python3", str(REMOTE), source]
                result = subprocess.run(command, stdout=output, stderr=subprocess.PIPE,
                                        timeout=120, check=False)
            if result.returncode:
                raise ValueError(result.stderr.decode(errors="replace").strip()[:300] or
                                 f"Argus backup source {source} failed")
            files[name] = {"sha256": digest(path), "bytes": path.stat().st_size}
        manifest = {"captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "files": files}
        (staging / "manifest.json").write_text(json.dumps(manifest, sort_keys=True) + "\n")
        os.chmod(staging / "manifest.json", 0o600)
        check_snapshot(staging)
        name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target = DESTINATION / name
        if target.exists():
            raise ValueError("backup name collision; retry in one second")
        staging.rename(target)
        return check_snapshot(target)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("create")
    verify = sub.add_parser("verify")
    verify.add_argument("folder", type=Path)
    args = parser.parse_args(argv)
    try:
        outcome = make_backup() if args.action == "create" else check_snapshot(args.folder)
        print(json.dumps(outcome, sort_keys=True))
        return 0
    except (OSError, ValueError, sqlite3.Error, tarfile.TarError, subprocess.TimeoutExpired) as error:
        print(f"argus-backup: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
