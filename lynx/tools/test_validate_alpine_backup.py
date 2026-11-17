#!/usr/bin/env python3
"""Unit tests for :func:`validate_receipt`.

The tests create a small tar.gz archive on the fly, generate a corresponding
JSON receipt with correct metadata, and verify that the validator accepts it.
Additional tests provide tampered archives and receipts to ensure that each
validation rule is exercised.
"""

from __future__ import annotations

import hashlib
import json
import os
import tarfile
import tempfile
from pathlib import Path
import io
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_alpine_backup import validate_receipt, EXPECTED_ROOTS


class TestValidateReceipt(unittest.TestCase):
    def setUp(self) -> None:
        # Create a temporary directory for the archive and receipt
        self.temp = Path(tempfile.mkdtemp())
        self.archive = self.temp / "test.tar.gz"
        self.receipt = self.temp / "test.json"
        # create one file per expected root
        self.contents = {f"{root}/file.txt": b"data" for root in EXPECTED_ROOTS}

        # Build archive
        with tarfile.open(self.archive, "w:gz") as tf:
            for name, data in self.contents.items():
                info = tarfile.TarInfo(name=name)
                info.size = len(data)
                tf.addfile(info, fileobj=io.BytesIO(data))

        # Compute metadata for receipt
        compressed_size = self.archive.stat().st_size
        sha256 = hashlib.sha256()
        with self.archive.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                sha256.update(chunk)
        compressed_hash = sha256.hexdigest()
        with self.archive.open("rb") as f:
            tar = tarfile.open(fileobj=f, mode="r:gz")
            member_count = len(tar.getmembers())
            roots = {Path(m.name).parts[0] for m in tar.getmembers()}
        # The validator expects the full set of expected roots
        receipt_data = {
            "compressed_bytes": compressed_size,
            "compressed_sha256": compressed_hash,
            "member_count": member_count,
            "roots": sorted(EXPECTED_ROOTS),
        }
        self.receipt.write_text(json.dumps(receipt_data))

    def tearDown(self) -> None:
        for p in [self.archive, self.receipt]:
            if p.exists():
                p.unlink()
        self.temp.rmdir()

    def test_valid(self) -> None:
        """The validator should accept a correct archive and receipt."""
        result = validate_receipt(self.archive, self.receipt)
        self.assertEqual(result["compressed_bytes"], self.archive.stat().st_size)
        # One file per expected root
        self.assertEqual(result["member_count"], len(EXPECTED_ROOTS))

    def test_wrong_compressed_size(self) -> None:
        """Alter the receipt to an incorrect size should fail."""
        data = json.loads(self.receipt.read_text())
        data["compressed_bytes"] = data["compressed_bytes"] + 1
        self.receipt.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            validate_receipt(self.archive, self.receipt)

    def test_wrong_sha256(self) -> None:
        """Corrupt the receipt hash should trigger a mismatch error."""
        data = json.loads(self.receipt.read_text())
        data["compressed_sha256"] = "0" * 64
        self.receipt.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            validate_receipt(self.archive, self.receipt)

    def test_missing_root(self) -> None:
        """A receipt missing a required root should fail."""
        data = json.loads(self.receipt.read_text())
        # remove "bin" from expected roots
        data["roots"] = [r for r in data["roots"] if r != "bin"]
        self.receipt.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            validate_receipt(self.archive, self.receipt)

    def test_traversal_path(self) -> None:
        """An archive containing a traversal path should be rejected."""
        # rebuild archive with a traversal path
        with tarfile.open(self.archive, "w:gz") as tf:
            for name, data in {"../evil": b"bad"}.items():
                info = tarfile.TarInfo(name=name)
                info.size = len(data)
                tf.addfile(info, fileobj=io.BytesIO(data))
        data = json.loads(self.receipt.read_text())
        data["compressed_bytes"] = self.archive.stat().st_size
        data["compressed_sha256"] = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        data["member_count"] = 1
        self.receipt.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "traversal path"):
            validate_receipt(self.archive, self.receipt)

    def test_missing_required_hash_is_rejected(self) -> None:
        data = json.loads(self.receipt.read_text())
        del data["compressed_sha256"]
        self.receipt.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "missing required"):
            validate_receipt(self.archive, self.receipt)

    def test_extra_archive_root_is_rejected(self) -> None:
        with tarfile.open(self.archive, "w:gz") as tf:
            for name, payload in {**self.contents, "extra/file.txt": b"bad"}.items():
                info = tarfile.TarInfo(name=name)
                info.size = len(payload)
                tf.addfile(info, fileobj=io.BytesIO(payload))
        data = json.loads(self.receipt.read_text())
        data["compressed_bytes"] = self.archive.stat().st_size
        data["compressed_sha256"] = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        data["member_count"] = len(EXPECTED_ROOTS) + 1
        self.receipt.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "archive roots"):
            validate_receipt(self.archive, self.receipt)
