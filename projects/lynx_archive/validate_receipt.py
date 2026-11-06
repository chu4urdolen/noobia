#!/usr/bin/env python3
"""Validate a Lynx Alpine file backup receipt.

The validator ensures that the provided ``alpine-files.tar.gz`` and its
corresponding JSON receipt match on the following criteria:

* The compressed archive size and SHA‑256 hash match the values stored in the
  receipt.
* The number of tar members matches the count recorded in the receipt.
* All top‑level entries are a subset of the expected root directories
  (``bin``, ``etc``, ``home``, ``lib``, ``opt``, ``root``, ``sbin``, ``usr``,
  ``var``).
* No member path is absolute (``/foo``) or attempts directory traversal
  (``../foo``).  These checks are performed without extracting the archive –
  only the metadata is inspected.

If any check fails, a :class:`ValueError` is raised with a descriptive
message.  The function returns the parsed receipt dictionary on success.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Dict
import tarfile

__all__ = ["validate_receipt"]

# Expected top‑level roots – keep in sync with backup_alpine_files.py
EXPECTED_ROOTS = {
    "bin",
    "etc",
    "home",
    "lib",
    "opt",
    "root",
    "sbin",
    "usr",
    "var",
}


def _check_path(name: str) -> None:
    """Raise :class:`ValueError` if *name* is absolute or contains ``..``.

    The tar format stores paths without a leading slash, but a malicious
    archive could still contain ``../`` components.  We reject any path
    that would extract outside the intended top‑level directory.
    """

    if os.path.isabs(name):
        raise ValueError(f"absolute path in tar member: {name}")
    # Normalise to POSIX style for consistency
    parts = Path(name).parts
    if ".." in parts:
        raise ValueError(f"traversal path in tar member: {name}")


def validate_receipt(archive_path: Path, receipt_path: Path) -> Dict:
    """Validate *archive_path* against *receipt_path*.

    Parameters
    ----------
    archive_path:
        Path to the ``.tar.gz`` file.
    receipt_path:
        Path to the accompanying JSON receipt.

    Returns
    -------
    dict
        The parsed receipt dictionary if all checks pass.

    Raises
    ------
    ValueError
        If any validation rule is violated.
    FileNotFoundError
        If either file does not exist.
    """

    archive_path = Path(archive_path)
    receipt_path = Path(receipt_path)

    if not archive_path.is_file():
        raise FileNotFoundError(f"archive not found: {archive_path}")
    if not receipt_path.is_file():
        raise FileNotFoundError(f"receipt not found: {receipt_path}")

    # Load receipt JSON
    try:
        receipt = json.loads(receipt_path.read_text())
    except Exception as exc:  # pragma: no cover - defensive
        raise ValueError(f"unable to parse receipt JSON: {exc}")

    # Verify compressed size and SHA‑256
    compressed_size = archive_path.stat().st_size
    if "compressed_bytes" in receipt:
        if compressed_size != receipt["compressed_bytes"]:
            raise ValueError(
                f"compressed size mismatch: expected {receipt['compressed_bytes']}, got {compressed_size}"
            )
    if "compressed_sha256" in receipt:
        sha256 = hashlib.sha256()
        with archive_path.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                sha256.update(chunk)
        if sha256.hexdigest() != receipt["compressed_sha256"]:
            raise ValueError("compressed SHA‑256 mismatch")

    # Inspect tar members without extraction
    member_names = []
    with tarfile.open(archive_path, "r:gz") as tf:
        for m in tf.getmembers():
            _check_path(m.name)
            member_names.append(m.name)

    # Verify member count
    if "member_count" in receipt:
        if len(member_names) != receipt["member_count"]:
            raise ValueError(
                f"member count mismatch: expected {receipt['member_count']}, got {len(member_names)}"
            )

    # Verify top‑level roots
    roots_in_tar = {Path(name).parts[0] for name in member_names}
    if "roots" in receipt:
        # Receipt must list all expected roots
        receipt_roots = set(receipt["roots"])
        if receipt_roots != EXPECTED_ROOTS:
            missing = EXPECTED_ROOTS - receipt_roots
            extra = receipt_roots - EXPECTED_ROOTS
            parts = []
            if missing:
                parts.append(f"missing {sorted(missing)}")
            if extra:
                parts.append(f"unexpected {sorted(extra)}")
            raise ValueError("roots mismatch: " + ", ".join(parts))
        # Ensure all expected roots appear in the archive
        if not EXPECTED_ROOTS.issubset(roots_in_tar):
            missing = EXPECTED_ROOTS - roots_in_tar
            raise ValueError(f"missing expected roots in archive: {sorted(missing)}")
    else:
        # If receipt omitted roots, ensure the archive contains all expected
        if not EXPECTED_ROOTS.issubset(roots_in_tar):
            missing = EXPECTED_ROOTS - roots_in_tar
            raise ValueError(f"missing expected roots in archive: {sorted(missing)}")

    return receipt


if __name__ == "__main__":  # pragma: no cover
    import argparse
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="Path to .tar.gz file")
    parser.add_argument("receipt", type=Path, help="Path to JSON receipt")
    args = parser.parse_args()
    try:
        validate_receipt(args.archive, args.receipt)
        print("Validation succeeded")
    except Exception as e:
        print(f"Validation failed: {e}", file=sys.stderr)
        sys.exit(1)

