"""Unittest suite for the :mod:`sparse_image` CLI.

The tests are intentionally lightweight and run with the standard
``python3 -m unittest discover -s projects/lynx_backup`` command.  They create a
temporary source file containing a mixture of zero and non‑zero byte blocks,
invoke the command line tool via :mod:`subprocess`, and then verify that the
destination file exactly mirrors the source in content and size.  A second
test checks that attempting to copy from a non‑existent source file causes the
script to exit with a non‑zero status.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
import unittest

SCRIPT = Path("projects/lynx_backup/sparse_image.py")
SRC = Path("projects/lynx_backup/tmp_src.bin")
DST = Path("projects/lynx_backup/tmp_dst.bin")


def make_source() -> bytes:
    """Return a byte sequence with leading, middle, and trailing zero blocks.

    Pattern: 10 zero bytes + ``b"hello"`` + 5 zero bytes + ``b"\x01\x02"`` + 3 zero bytes.
    """

    return b"\x00" * 10 + b"hello" + b"\x00" * 5 + b"\x01\x02" + b"\x00" * 3


class TestSparseImage(unittest.TestCase):
    def tearDown(self) -> None:
        for p in (SRC, DST):
            if p.exists():
                p.unlink()

    def test_sparse_copy(self):
        # Write source file
        SRC.write_bytes(make_source())
        # Run script via subprocess
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(SRC), str(DST)],
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr.decode())
        # Compare content and size
        dst_bytes = DST.read_bytes()
        self.assertEqual(dst_bytes, make_source())
        self.assertEqual(DST.stat().st_size, SRC.stat().st_size)

    def test_missing_source(self):
        # Ensure source does not exist
        if SRC.exists():
            SRC.unlink()
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(SRC), str(DST)],
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

