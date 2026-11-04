"""Lynx camera frame comparison utilities.

This module implements a lightweight offline comparison tool for raw camera
frames.  It is intentionally simple – only pure Python and the standard
library are used – so that it can run on the limited resources of the
workspace environment.

The :func:`compare_frames` function performs the following steps:

1. **Validate inputs** – ensure the provided width/height are positive, the
   black level is a non‑negative integer, and the two buffers contain the
   same number of bytes equal to ``width * height``.
2. **Compute raw means** – the average of all byte values in each frame.
3. **Compute signal means** – the average of ``max(byte - black_level, 0)`` for
   each frame.  This represents the *positive* signal after subtracting the
   camera black level.
4. **Compute signal ratio** – ``signal_mean_first / signal_mean_second``.  If
   the second mean is zero the ratio is ``None``; if the first mean is zero the
   ratio is also ``None``.
5. **Compute a 4×4 diff grid** – the mean raw difference between the two
   frames for each 4‑by‑4 block of pixels.  The image dimensions must be
   divisible by four; otherwise a :class:`ValueError` is raised.

The function returns a JSON‑serialisable dictionary containing the
statistics.  The module also provides a small command‑line interface that
accepts two file paths and prints the comparison result.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Dict, List

__all__ = ["compare_frames"]


def _validate_dimensions(width: int, height: int) -> None:
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be positive integers")
    if width % 4 != 0 or height % 4 != 0:
        raise ValueError("width and height must be divisible by 4 for diff grid")


def compare_frames(
    first: bytes,
    second: bytes,
    width: int,
    height: int,
    black_level: int = 16,
):
    """Compare two raw camera frames.

    Parameters
    ----------
    first, second:
        Raw frame buffers as ``bytes``.
    width, height:
        Dimensions of the image.  Must be positive and divisible by four.
    black_level:
        The black level to subtract when computing the signal mean.

    Returns
    -------
    dict
        JSON‑compatible dictionary with the following keys:
        ``raw_mean1``, ``raw_mean2``, ``signal_mean1``, ``signal_mean2``,
        ``signal_ratio`` (``None`` if undefined) and ``diff_grid`` – a
        4×4 list of floats representing the mean raw difference per block.
    """

    # Input validation
    if black_level < 0:
        raise ValueError("black_level must be non‑negative")
    _validate_dimensions(width, height)

    expected_len = width * height
    if len(first) != expected_len or len(second) != expected_len:
        raise ValueError(
            f"frame sizes must equal width*height ({expected_len}); got {len(first)} and {len(second)}"
        )

    # Raw means
    raw_mean1 = sum(first) / expected_len
    raw_mean2 = sum(second) / expected_len

    # Signal means – clip negative values to zero
    def _signal_mean(buf: bytes) -> float:
        return sum(max(b - black_level, 0) for b in buf) / expected_len

    signal_mean1 = _signal_mean(first)
    signal_mean2 = _signal_mean(second)

    # Signal ratio
    if signal_mean1 == 0 or signal_mean2 == 0:
        signal_ratio = None
    else:
        signal_ratio = signal_mean1 / signal_mean2

    # Diff grid – 4x4 blocks
    block_w = width // 4
    block_h = height // 4
    diff_grid: List[List[float]] = []
    for by in range(4):
        row: List[float] = []
        for bx in range(4):
            # Compute mean difference for block
            start_x = bx * block_w
            start_y = by * block_h
            total = 0
            for y in range(start_y, start_y + block_h):
                offset = y * width + start_x
                for x in range(block_w):
                    total += first[offset + x] - second[offset + x]
            mean_diff = total / (block_w * block_h)
            row.append(mean_diff)
        diff_grid.append(row)

    return {
        "raw_mean1": raw_mean1,
        "raw_mean2": raw_mean2,
        "signal_mean1": signal_mean1,
        "signal_mean2": signal_mean2,
        "signal_ratio": signal_ratio,
        "diff_grid": diff_grid,
    }


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Compare two Lynx camera raw frames")
    parser.add_argument("first", help="Path to first raw frame file")
    parser.add_argument("second", help="Path to second raw frame file")
    parser.add_argument("--width", type=int, required=True, help="Frame width in pixels")
    parser.add_argument("--height", type=int, required=True, help="Frame height in pixels")
    parser.add_argument("--black-level", type=int, default=16, help="Black level to subtract")
    args = parser.parse_args()

    try:
        with open(args.first, "rb") as f:
            first_bytes = f.read()
        with open(args.second, "rb") as f:
            second_bytes = f.read()
        result = compare_frames(first_bytes, second_bytes, args.width, args.height, args.black_level)
        print(json.dumps(result, indent=2))
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    _cli()

