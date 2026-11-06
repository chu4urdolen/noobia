#!/usr/bin/env python3
"""sparse_image
================

This script copies a regular source file to a destination file, creating a
*sparse* copy.  It copies the exact byte contents, but for sequences of all
zero bytes it uses ``os.lseek`` to skip writing the data, thereby creating a
hole in the destination file.  The destination file ends up with the same
length as the source.

Usage
-----
```
python3 sparse_image.py SOURCE DEST
```

The script exits with status 0 on success and a non‑zero status if an error
occurs (e.g. missing source file, permission error, etc.).

The implementation deliberately uses only the standard library and works on
POSIX filesystems that support sparse files (Linux, macOS, FreeBSD).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

CHUNK_SIZE = 64 * 1024  # 64 KiB chunks for efficient copying


def copy_sparse(src: Path, dst: Path) -> None:
    """Copy *src* to *dst* using sparse write technique.

    Parameters
    ----------
    src:
        Path to the source file.
    dst:
        Path to the destination file.  Existing files are overwritten.
    """

    if not src.is_file():
        raise FileNotFoundError(f"Source file does not exist: {src}")

    # Reject copy if source and destination are the same path to avoid destructive overwrite
    if src.resolve() == dst.resolve():
        raise ValueError("Source and destination refer to the same file; aborting to protect data.")

    # Reject if destination already exists (including symlink or hard‑link alias)
    if dst.exists() or dst.is_symlink() or dst.is_file():
        # also check for hard‑link alias
        try:
            if src.samefile(dst):
                raise FileExistsError("Source and destination are hard‑link aliases; aborting.")
        except OSError:
            # samefile may fail if file missing; ignore
            pass
        raise FileExistsError("Destination already exists; aborting to protect data.")

    # Ensure destination directory exists
    dst.parent.mkdir(parents=True, exist_ok=True)

    bytes_written = 0
    # Open destination exclusively to ensure no race condition
    with src.open("rb") as fsrc, dst.open("xb") as fdst:
        while True:
            chunk = fsrc.read(CHUNK_SIZE)
            if not chunk:
                break
            if set(chunk) == {0}:
                # All zero bytes – seek over the chunk length
                fdst.seek(len(chunk), os.SEEK_CUR)
            else:
                fdst.write(chunk)
                # Count bytes passed to write(), including zeros in mixed chunks.
                bytes_written += len(chunk)

    # Ensure the destination file size matches the source
    src_size = src.stat().st_size
    dst_size = dst.stat().st_size
    if src_size != dst_size:
        # Adjust size if the sparse hole logic skipped beyond the expected size
        # Use an open file handle for truncate
        with dst.open("r+b") as fdst:
            fdst.truncate(src_size)

    # Print a short success report
    print(f"Sparse copy succeeded: source size={src_size} bytes, bytes_written={bytes_written} bytes")


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if len(argv) != 2:
        print("Usage: sparse_image.py SOURCE DEST", file=sys.stderr)
        return 1
    src, dst = map(Path, argv)
    try:
        copy_sparse(src, dst)
    except Exception as exc:  # pragma: no cover – defensive
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

