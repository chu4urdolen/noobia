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
        # Contiguous chunks – no gap, no overlap
        _make_chunk(self.dir, "sda", 0, b"a" * 1024)
        _make_chunk(self.dir, "sda", 1024, b"b" * 512)
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

    def test_plan_file_ignored(self):
        """Plan JSON files should be ignored and not counted as receipts."""
        (self.dir / "sda-plan.json").write_text(json.dumps({"device": "sda", "size": 1024, "chunk_size": 1024}))
        _make_chunk(self.dir, "sda", 0, b"a" * 1024)
        result = verify_directory(self.dir)
        self.assertTrue(result.valid)
        self.assertEqual(result.total_chunks, 1)
        self.assertEqual(result.total_raw_bytes, 1024)

    def test_unmatched_gzip(self):
        """A gzip file without a receipt should trigger an error."""
        gz_path = self.dir / "orphan.gz"
        with gz_path.open("wb") as f:
            with gzip.GzipFile(fileobj=f, mode="wb") as gz:
                gz.write(b"x" * 512)
        result = verify_directory(self.dir)
        self.assertFalse(result.valid)
        self.assertTrue(any("Unmatched gzip file" in e for e in result.errors))

    def test_same_device_no_gap(self):
        """Chunks of the same device that touch but do not overlap are OK."""
        _make_chunk(self.dir, "sda", 0, b"a" * 1024)
        _make_chunk(self.dir, "sda", 1024, b"b" * 512)
        result = verify_directory(self.dir)
        self.assertTrue(result.valid)

    def test_gap_between_chunks(self):
        """A gap between chunks of the same device should raise an error."""
        _make_chunk(self.dir, "sda", 0, b"a" * 1024)
        _make_chunk(self.dir, "sda", 2048, b"b" * 512)
        result = verify_directory(self.dir)
        self.assertFalse(result.valid)
        self.assertTrue(any("Gap between chunks" in e for e in result.errors))

    # New plan‑aware tests -------------------------------------------------
    def _write_plan(self, device: str, size: int, chunk_size: int):
        plan_path = self.dir / f"{device}-plan.json"
        plan_path.write_text(json.dumps({"size": size, "chunk_size": chunk_size}))

    def test_plan_complete_two_chunks(self):
        """Two contiguous chunks cover the plan size – progress shows complete."""
        self._write_plan("sda", 1536, 1024)
        _make_chunk(self.dir, "sda", 0, b"a" * 1024)
        _make_chunk(self.dir, "sda", 1024, b"b" * 512)
        result = verify_directory(self.dir)
        self.assertTrue(result.valid)
        self.assertIn("sda", result.device_progress)
        self.assertTrue(result.device_progress["sda"]["complete"])
        self.assertEqual(result.device_progress["sda"]["saved_bytes"], 1536)
        self.assertEqual(result.device_progress["sda"]["total_bytes"], 1536)

    def test_plan_partial_single_chunk(self):
        """Single chunk less than plan size – progress incomplete."""
        self._write_plan("sda", 2048, 1024)
        _make_chunk(self.dir, "sda", 0, b"a" * 1024)
        result = verify_directory(self.dir)
        self.assertTrue(result.valid)
        self.assertFalse(result.device_progress["sda"]["complete"])
        self.assertEqual(result.device_progress["sda"]["saved_bytes"], 1024)
        self.assertEqual(result.device_progress["sda"]["total_bytes"], 2048)

    def test_nonzero_first_offset(self):
        """Plan present but first chunk does not start at zero – error reported."""
        self._write_plan("sda", 2048, 1024)
        _make_chunk(self.dir, "sda", 512, b"a" * 1024)
        result = verify_directory(self.dir)
        self.assertFalse(result.valid)
        self.assertTrue(any("First chunk" in e for e in result.errors))

    def test_malformed_plan_is_error(self):
        (self.dir / "sda-plan.json").write_text(json.dumps({"device": "sda", "size": -1, "chunk_size": 1024}))
        result = verify_directory(self.dir)
        self.assertFalse(result.valid)
        self.assertTrue(any("Invalid plan" in e for e in result.errors))

    def test_malformed_receipt_offset(self):
        """Receipt contains non‑int offset – error reported."""
        self._write_plan("sda", 1024, 1024)
        # Write a valid chunk
        _make_chunk(self.dir, "sda", 0, b"a" * 1024)
        # Corrupt the receipt offset to a string
        receipt_path = self.dir / "chunk-0.json"
        data = json.loads(receipt_path.read_text())
        data["offset"] = "zero"
        receipt_path.write_text(json.dumps(data))
        result = verify_directory(self.dir)
        self.assertFalse(result.valid)
        self.assertTrue(any("invalid offset or raw_size" in e for e in result.errors))


if __name__ == "__main__":
    unittest.main()

