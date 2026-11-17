#!/usr/bin/env python3
"""Wait for the raw Lynx reader, then take a guarded Alpine file archive.

No phone writes. Exits without archiving if the raw read is incomplete,
Lynx is unhealthy, or the battery is below the file-backup reserve.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time

from backup_alpine_files import save
from backup_full_ufs import CHUNK, SIZES, health


ROOT = Path("/noobia/lynx")
RAW = ROOT / "backups/full-ufs-20261106-v53"
FILES = ROOT / "backups/alpine-files-20261107-v53"
REPORT = ROOT / "logs/backup-finish-20261107.json"
SERVICE = "lynx-ufs-final-backup.service"


def active():
    result = subprocess.run(["systemctl", "--user", "is-active", SERVICE],
                            capture_output=True, text=True)
    return result.stdout.strip() == "active"


def complete():
    if list(RAW.glob("*.part")):
        raise RuntimeError("raw backup has a partial file")
    expected = range(0, SIZES["sdc"], CHUNK)
    for offset in expected:
        stem = f"sdc-{offset:012d}"
        if not (RAW / f"{stem}.json").is_file() or not (RAW / f"{stem}.gz").is_file():
            raise RuntimeError(f"raw backup incomplete at {stem}")


def main():
    record = {"state": "waiting", "raw_service": SERVICE,
              "started_utc": datetime.now(timezone.utc).isoformat()}
    try:
        deadline = time.monotonic() + 7200
        while active():
            if time.monotonic() >= deadline:
                raise RuntimeError("raw backup exceeded two-hour wait")
            time.sleep(30)
        complete()
        state = health()
        if state["issues"] or state["battery"]["capacity_percent"] < 47:
            raise RuntimeError("Alpine file backup health or 47% battery gate failed")
        archived = save(FILES)
        record.update(state="file-archive-verified", boot_id=archived["boot_id"],
                      archive=str(FILES / "alpine-files.tar.gz"),
                      receipt=str(FILES / "alpine-files.json"),
                      compressed_sha256=archived["compressed_sha256"])
    except Exception as error:
        record.update(state="stopped-before-file-archive", reason=str(error))
    finally:
        record["finished_utc"] = datetime.now(timezone.utc).isoformat()
        REPORT.write_text(json.dumps(record, indent=2) + "\n")
        REPORT.chmod(0o600)
        print(json.dumps(record), flush=True)
    return 0 if record["state"] == "file-archive-verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
