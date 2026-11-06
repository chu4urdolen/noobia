"""Unit tests for :mod:`projects.lynx_backup.audit_chunks`.

The tests create temporary directories with synthetic gzip/JSON receipt pairs
to cover the following scenarios:

* **Valid chunks** – two non‑overlapping chunks that satisfy all checks.
* **Truncated gzip** – a chunk whose compressed payload is cut short; the
  decompression should raise a CRC error.
* **Wrong hash** – a chunk whose receipt contains an incorrect SHA‑256.
* **Overlapping chunks** – a receipt with an offset that overlaps a
  previous chunk.

The tests use :mod:`tempfile` to create isolated file systems and assert
that :func:`verify_directory` reports the expected errors.
"""

from __future__ import annotations

import gzip
import json
import hashlib
import os
import pathlib
import shutil
import tempfile
import unittest
from pathlib import Path

from projects.lynx_backup.audit_chunks import verify_directory


def _make_chunk(dir_path: Path, device: str, offset: int, raw: bytes) -> None:
    gz_path = dir_path / f"chunk-{offset}.gz"
    with gz_path.open("wb") as f_out:
        with gzip.GzipFile(fileobj=f_out, mode="wb") as gz:
            gz.write(raw)
    receipt = {
        "device": device,
        "offset": offset,
        "raw_size": len(raw),
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
    }
    (dir_path / f"chunk-{offset}.json").write_text(json.dumps(receipt))


class TestAuditChunks(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_valid_chunks(self):
        _make_chunk(self.dir, "sda", 0, b"a" * 1024)
        _make_chunk(self.dir, "sda", 2048, b"b" * 512)
        result = verify_directory(self.dir)
        self.assertTrue(result.valid)
        self.assertEqual(result.total_chunks, 2)
        self.assertEqual(result.total_raw_bytes, 1536)
        self.assertFalse(result.errors)

    def test_truncated_gzip(self):
        raw = b"x" * 1024
        gz_path = self.dir / "chunk-0.gz"
        with gz_path.open("wb") as f_out:
            with gzip.GzipFile(fileobj=f_out, mode="wb") as gz:
                gz.write(raw)
        # Truncate the file to a small size to trigger a decompression error.
        os.truncate(gz_path, 10)
        receipt = {
            "device": "sda",
            "offset": 0,
            "raw_size": len(raw),
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
        }
        (self.dir / "chunk-0.json").write_text(json.dumps(receipt))
        result = verify_directory(self.dir)
        self.assertFalse(result.valid)
        self.assertTrue(any("Failed to decompress" in e for e in result.errors))

    def test_wrong_hash(self):
        raw = b"z" * 2048
        _make_chunk(self.dir, "sda", 0, raw)
        # Corrupt the receipt hash
        (self.dir / "chunk-0.json").write_text(json.dumps({
            "device": "sda",
            "offset": 0,
            "raw_size": len(raw),
            "raw_sha256": "deadbeef",
        }))
        result = verify_directory(self.dir)
        self.assertFalse(result.valid)
        self.assertTrue(any("SHA256 mismatch" in e for e in result.errors))

    def test_overlapping_chunks(self):
        _make_chunk(self.dir, "sda", 0, b"a" * 1024)
        # Overlap: offset 512 within the first chunk's size 1024
        _make_chunk(self.dir, "sda", 512, b"b" * 512)
        result = verify_directory(self.dir)
        self.assertFalse(result.valid)
        self.assertTrue(any("Overlapping chunks" in e for e in result.errors))


if __name__ == "__main__":
    unittest.main()

