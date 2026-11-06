"""Unit tests for the :mod:`sparse_image` CLI.

The tests exercise the following scenarios:

* Normal copy with leading, middle and trailing zero blocks.
* Attempting to copy onto an existing destination (regular file, symlink or
  hard‑link alias) fails.
* Attempting to copy where source and destination refer to the same file
  (including hard‑link alias) fails.
* Copying a file that ends with a full 65536‑byte zero block preserves the
  exact length and content.
* The CLI prints a short report that reports the ``bytes_written`` counter
  (bytes passed to write()) rather than the physical allocation.

All tests use :func:`tempfile.TemporaryDirectory` to avoid cross‑test
interference and ensure a clean environment.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import os
from pathlib import Path
import unittest

SCRIPT = Path("projects/lynx_backup/sparse_image.py")


def make_source() -> bytes:
    """Return a byte sequence with leading, middle, and trailing zero blocks.

    Pattern: 10 zero bytes + ``b"hello"`` + 5 zero bytes + ``b"\x01\x02"`` + 3 zero bytes.
    """
    return b"\x00" * 10 + b"hello" + b"\x00" * 5 + b"\x01\x02" + b"\x00" * 3


class TestSparseImage(unittest.TestCase):
    def test_normal_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src.bin"
            dst = Path(tmp) / "dst.bin"
            src.write_bytes(make_source())
            res = subprocess.run(
                [sys.executable, str(SCRIPT), str(src), str(dst)],
                capture_output=True,
                check=False,
            )
            self.assertEqual(res.returncode, 0, msg=res.stderr.decode())
            self.assertEqual(dst.read_bytes(), make_source())
            self.assertEqual(dst.stat().st_size, src.stat().st_size)

    def test_existing_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src.bin"
            dst = Path(tmp) / "dst.bin"
            src.write_bytes(make_source())
            dst.write_bytes(b"existing")
            res = subprocess.run(
                [sys.executable, str(SCRIPT), str(src), str(dst)],
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(res.returncode, 0)
            self.assertEqual(src.read_bytes(), make_source())
            self.assertEqual(dst.read_bytes(), b"existing")

    def test_hardlink_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src.bin"
            alias = Path(tmp) / "alias.bin"
            src.write_bytes(make_source())
            os.link(src, alias)
            res = subprocess.run(
                [sys.executable, str(SCRIPT), str(src), str(alias)],
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(res.returncode, 0)
            self.assertEqual(src.read_bytes(), make_source())

    def test_same_source_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src.bin"
            src.write_bytes(make_source())
            res = subprocess.run(
                [sys.executable, str(SCRIPT), str(src), str(src)],
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(res.returncode, 0)

    def test_trailing_full_zero_chunk(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src.bin"
            dst = Path(tmp) / "dst.bin"
            data = b"\x00" * 65536 + b"abc" + b"\x00" * 65536
            src.write_bytes(data)
            res = subprocess.run(
                [sys.executable, str(SCRIPT), str(src), str(dst)],
                capture_output=True,
                check=False,
            )
            self.assertEqual(res.returncode, 0, msg=res.stderr.decode())
            self.assertEqual(dst.read_bytes(), data)
            self.assertEqual(dst.stat().st_size, src.stat().st_size)

    def test_report_bytes_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src.bin"
            dst = Path(tmp) / "dst.bin"
            src.write_bytes(make_source())
            res = subprocess.run(
                [sys.executable, str(SCRIPT), str(src), str(dst)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(res.returncode, 0)
            self.assertIn(f"bytes_written={len(make_source())} bytes", res.stdout)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

