"""Offline checks for the read-only Lynx UFS backup receiver."""

import gzip
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import backup_full_ufs as backup


class FakeProcess:
    def __init__(self, data: bytes, code: int = 0):
        self.stdout = io.BytesIO(data)
        self.stderr = io.BytesIO(b"")
        self.code = code

    def wait(self, timeout=None):
        return self.code

    def kill(self):
        pass


class BackupChunkTests(unittest.TestCase):
    def test_valid_chunk_and_receipt(self):
        raw = b"\0" * backup.MIB + b"abc" + b"\0" * (backup.MIB - 3)
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(backup.subprocess, "Popen", return_value=FakeProcess(gzip.compress(raw))):
                receipt = backup.save_chunk(Path(tmp), "sdc", 0, len(raw))
            final = Path(tmp) / "sdc-000000000000.gz"
            self.assertEqual(receipt["raw_sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(receipt["raw_size"], len(raw))
            backup.verify_gzip(final, len(raw), receipt["raw_sha256"])
            self.assertFalse(final.with_suffix(".gz.part").exists())
            self.assertEqual(final.stat().st_mode & 0o777, 0o600)

    def test_truncated_stream_is_not_published(self):
        raw = b"x" * backup.MIB
        compressed = gzip.compress(raw)[:-4]
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(backup.subprocess, "Popen", return_value=FakeProcess(compressed)):
                with self.assertRaises(ValueError):
                    backup.save_chunk(Path(tmp), "sdc", 0, len(raw))
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            final = Path(tmp) / "sdc-000000000000.gz"
            final.write_bytes(b"existing")
            with self.assertRaises(FileExistsError):
                backup.save_chunk(Path(tmp), "sdc", 0, backup.MIB)
            self.assertEqual(final.read_bytes(), b"existing")


if __name__ == "__main__":
    unittest.main()
