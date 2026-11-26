#!/usr/bin/env python3
"""Stream a consistent Argus evidence backup over an authenticated SSH session."""

import argparse
import os
from pathlib import Path
import sqlite3
import sys
import tarfile
import tempfile


NOOBIA = Path(os.environ.get("NOOBIA", "/noobia"))
SOURCES = {"history": NOOBIA / "argus/data/history.sqlite3",
           "jobs": NOOBIA / "argus/data/jobs.sqlite3"}
STATION_FILES = {
    "station/AGENTS-root.md": NOOBIA / "AGENTS.md",
    "station/AGENTS-argus.md": NOOBIA / "argus/AGENTS.md",
    "station/AGENTS-common.md": NOOBIA / "common/AGENTS.md",
    "station/launch": NOOBIA / "argus/launch",
    "station/desktop-items-HDMI-A-1.conf": Path("/home/argus/.config/pcmanfm/default/desktop-items-HDMI-A-1.conf"),
    "station/Argus.png": NOOBIA / "pics/Argus/Argus.png",
    "station/argus-historian-worker.service": Path("/etc/systemd/system/argus-historian-worker.service"),
}


def stream_database(name):
    source = SOURCES[name]
    with tempfile.NamedTemporaryFile(prefix=".argus-backup-", suffix=".sqlite3",
                                     dir=source.parent, delete=False) as file:
        temporary = Path(file.name)
    try:
        os.chmod(temporary, 0o600)
        with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as live, \
             sqlite3.connect(temporary) as copy:
            live.backup(copy)
        with temporary.open("rb") as file:
            while chunk := file.read(1024 * 1024):
                sys.stdout.buffer.write(chunk)
    finally:
        temporary.unlink(missing_ok=True)


def stream_archive():
    archive = NOOBIA / "archive"
    if not archive.is_dir():
        raise ValueError("Argus archive missing")
    with tarfile.open(fileobj=sys.stdout.buffer, mode="w|") as tar:
        tar.add(archive, arcname="archive", recursive=True)


def stream_station():
    with tarfile.open(fileobj=sys.stdout.buffer, mode="w|") as tar:
        for name, source in STATION_FILES.items():
            if not source.is_file() or source.is_symlink():
                raise ValueError(f"station file unavailable: {source}")
            tar.add(source, arcname=name, recursive=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", choices=("history", "jobs", "archive", "station"))
    args = parser.parse_args()
    try:
        if args.source == "archive":
            stream_archive()
        elif args.source == "station":
            stream_station()
        else:
            stream_database(args.source)
        return 0
    except (OSError, sqlite3.Error, ValueError) as error:
        print(f"argus-backup-source: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
