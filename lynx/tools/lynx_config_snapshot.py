#!/usr/bin/env python3
"""lynx_config_snapshot: Snapshot Lynx config, patterns & reflexes with restore drill (NA-70)."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile
import time


def calculate_sha256(file_path: Path) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def create_snapshot(source_paths: list[Path], output_tar: Path) -> dict:
    """Create a tar.gz snapshot of listed configuration directories and files."""
    output_tar.parent.mkdir(parents=True, exist_ok=True)
    manifest = {}

    with tarfile.open(output_tar, "w:gz") as tar:
        for p in source_paths:
            if not p.exists():
                continue
            if p.is_dir():
                for sub in p.rglob("*"):
                    if sub.is_file():
                        arcname = str(sub.relative_to(p.parent))
                        tar.add(sub, arcname=arcname)
                        manifest[arcname] = calculate_sha256(sub)
            else:
                arcname = p.name
                tar.add(p, arcname=arcname)
                manifest[arcname] = calculate_sha256(p)

    return {
        "ok": True,
        "archive": str(output_tar),
        "files_count": len(manifest),
        "manifest": manifest,
        "size_bytes": output_tar.stat().st_size
    }


def verify_restore_drill(snapshot_tar: Path, expected_manifest: dict) -> dict:
    """Verify archive integrity by extracting to disposable sandbox and checking SHA256."""
    with tempfile.TemporaryDirectory() as tmpdir:
        sandbox = Path(tmpdir)
        with tarfile.open(snapshot_tar, "r:gz") as tar:
            tar.extractall(path=sandbox)

        mismatches = []
        for rel_path, expected_hash in expected_manifest.items():
            extracted = sandbox / rel_path
            if not extracted.is_file():
                mismatches.append(f"Missing file: {rel_path}")
                continue
            actual_hash = calculate_sha256(extracted)
            if actual_hash != expected_hash:
                mismatches.append(f"Hash mismatch on {rel_path}")

        if mismatches:
            return {"ok": False, "drill_passed": False, "errors": mismatches}

        return {"ok": True, "drill_passed": True, "verified_files": len(expected_manifest)}


def main():
    sources = [
        Path("/etc/noobia"),
        Path("/etc/lynx"),
        Path("/var/lib/noobia/autonomy/patterns.json"),
        Path("/var/lib/noobia/reflex/reflexes.db")
    ]
    ts = int(time.time())
    dest_dir = Path("/var/backups/lynx")
    out_file = dest_dir / f"lynx-config-snapshot-{ts}.tar.gz"

    res = create_snapshot(sources, out_file)
    drill = verify_restore_drill(out_file, res["manifest"])

    res["drill"] = drill
    print(json.dumps(res, indent=2))
    return 0 if drill["drill_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
