#!/usr/bin/env python3
"""Create a private, verified file-level Alpine backup over pinned SSH.

Run only after the raw UFS reader stops. This reads Lynx's live ext4 root;
the archive is a recovery aid, not an atomic filesystem snapshot.
"""

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

from backup_full_ufs import PHONE, PHONE_SERIAL, V53_BOOT_SHA256, health
from lynx_wifi_v19_contact import ssh_command
from validate_alpine_backup import validate_receipt


ROOTS = ("bin", "etc", "home", "lib", "opt", "root", "sbin", "usr", "var")
BACKUP_ROOT = Path("/noobia/lynx/backups")


def preflight():
    active = subprocess.run(["systemctl", "--user", "list-units",
                             "lynx-ufs-*.service", "--state=running",
                             "--no-legend", "--no-pager"],
                            capture_output=True, text=True, check=True)
    if active.stdout.strip():
        raise RuntimeError("raw UFS backup is active; run file backup afterward")
    state = health()
    if state["issues"] or state["battery"]["capacity_percent"] < 40:
        raise RuntimeError("Lynx health or battery gate failed")
    root = state["root_filesystem"]
    if root["source"] != "/dev/sdc85" or root["type"] != "ext4":
        raise RuntimeError("unexpected Alpine root filesystem")
    command = ("sed -n 's/.*oplusboot.serialno=\\([^ ]*\\).*/\\1/p' /proc/cmdline; "
               "sha256sum /dev/sdc39 | cut -c1-64; cat /proc/sys/kernel/random/boot_id; "
               "awk '{print $2}' /proc/mounts")
    argv = ssh_command(PHONE, command)
    argv[-2:-2] = ["-p", "2222"]
    result = subprocess.run(argv, capture_output=True, timeout=30, check=True)
    serial, boot_sha, boot_id, *mounts = result.stdout.decode().splitlines()
    if serial != PHONE_SERIAL or boot_sha != V53_BOOT_SHA256 or boot_id != state["boot_id"]:
        raise RuntimeError("phone or V53 boot identity changed")
    for mount in mounts:
        if any(mount == "/" + name or mount.startswith("/" + name + "/") for name in ROOTS):
            if mount != "/":
                raise RuntimeError(f"nested mount under selected Alpine roots: {mount}")
    return state


def save(out: Path):
    state = preflight()
    out = out.resolve()
    if not out.is_relative_to(BACKUP_ROOT):
        raise RuntimeError("output must be under /noobia/lynx/backups")
    out.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(out, 0o700)
    archive = out / "alpine-files.tar.gz"
    partial = out / "alpine-files.tar.gz.part"
    receipt = out / "alpine-files.json"
    if any(path.exists() for path in (archive, partial, receipt)):
        raise FileExistsError("archive, receipt, or partial already exists")
    command = "tar -C / -cf - " + " ".join(ROOTS)
    argv = ssh_command(PHONE, command)
    argv[-2:-2] = ["-p", "2222", "-T", "-o", "ServerAliveInterval=10",
                    "-o", "ServerAliveCountMax=3"]
    process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    raw_hash = hashlib.sha256()
    raw_bytes = 0
    try:
        with partial.open("xb") as file:
            os.chmod(partial, 0o600)
            with gzip.GzipFile(filename="", mode="wb", fileobj=file,
                               compresslevel=1, mtime=0) as stream:
                assert process.stdout is not None
                while block := process.stdout.read(1024 * 1024):
                    stream.write(block)
                    raw_hash.update(block)
                    raw_bytes += len(block)
            file.flush()
            os.fsync(file.fileno())
        assert process.stderr is not None
        error = process.stderr.read(4096)
        code = process.wait(timeout=30)
        if code:
            raise RuntimeError(f"remote tar failed: exit={code}, stderr={error!r}")
        if raw_bytes < 1024 * 1024:
            raise RuntimeError("Alpine archive unexpectedly small")
        compressed_hash = hashlib.sha256()
        with partial.open("rb") as file:
            while block := file.read(1024 * 1024):
                compressed_hash.update(block)
        with tarfile.open(partial, "r:gz") as contents:
            members = contents.getmembers()
            names = {member.name.split("/", 1)[0] for member in members}
            if not set(ROOTS).issubset(names):
                raise RuntimeError("archive root set incomplete")
        record = {"created_utc": datetime.now(timezone.utc).isoformat(),
                  "boot_id": state["boot_id"], "device_serial": PHONE_SERIAL,
                  "boot_sha256": V53_BOOT_SHA256, "root_source": "/dev/sdc85",
                  "roots": list(ROOTS), "raw_tar_bytes": raw_bytes,
                  "raw_tar_sha256": raw_hash.hexdigest(),
                  "compressed_bytes": partial.stat().st_size,
                  "compressed_sha256": compressed_hash.hexdigest(),
                  "member_count": len(members), "live_filesystem": True}
        receipt_part = out / "alpine-files.json.part"
        receipt_part.write_text(json.dumps(record, indent=2) + "\n")
        os.chmod(receipt_part, 0o600)
        validate_receipt(partial, receipt_part)
        archive_part = partial
        archive_part.rename(archive)
        receipt_part.rename(receipt)
        return record
    except BaseException:
        if process.poll() is None:
            process.kill()
        process.wait()
        partial.unlink(missing_ok=True)
        (out / "alpine-files.json.part").unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    options = parser.parse_args()
    try:
        result = save(options.out)
        print(json.dumps({"state": "verified", "receipt": str(options.out / "alpine-files.json"),
                          "members": result["member_count"]}))
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
