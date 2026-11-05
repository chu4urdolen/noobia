"""Utilities for computing channel means over a rectangular ROI in a Bayer frame.

The function :func:`roi_bayer_means` works with 8‑bit BGGR or RGGB Bayer
images.  It accepts a ``bytes`` frame, its width and height, and an even‑aligned
rectangular region defined by ``x0, y0, x1, y1``.  The function validates
that the image dimensions and ROI are positive even integers and that the ROI
lies within the image bounds.  Only the mean of each channel is returned – a
``dict`` mapping ``"B"``, ``"G1"``, ``"G2"`` and ``"R"`` to a floating point
average.

The implementation is deliberately straightforward and uses only the Python
standard library.
"""

from __future__ import annotations

from typing import Dict

__all__ = ["roi_bayer_means"]


def roi_bayer_means(
    frame: bytes,
    width: int,
    height: int,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    phase: str = "rggb",
) -> Dict[str, float]:
    """Return the mean pixel value for each Bayer channel within the ROI.

    Parameters
    ----------
    frame:
        Raw 8‑bit Bayer data.
    width, height:
        Image dimensions; must be positive even integers.
    x0, y0, x1, y1:
        Top‑left and bottom‑right coordinates of the ROI.  ``x1`` and ``y1`` are
        exclusive.  All coordinates must be even and lie within the image.
    phase:
        Either ``"bggr"`` or ``"rggb"``.  Other values raise :class:`ValueError`.

    Returns
    -------
    dict
        Mapping of channel names to mean values.
    """

    # Basic validation
    for name, val in {"width": width, "height": height}.items():
        if val <= 0 or val % 2:
            raise ValueError(f"{name} must be a positive even integer")
    expected_len = width * height
    if len(frame) != expected_len:
        raise ValueError("frame size does not match width*height")

    # ROI validation
    for coord, name in [(x0, "x0"), (y0, "y0"), (x1, "x1"), (y1, "y1")]:
        if coord % 2:
            raise ValueError(f"{name} must be even")
    if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
        raise ValueError("ROI bounds out of image")

    # Phase check
    phase = phase.lower()
    if phase not in ("bggr", "rggb"):
        raise ValueError("phase must be 'bggr' or 'rggb'")

    # Prepare accumulators
    sums = {"B": 0, "G1": 0, "G2": 0, "R": 0}
    counts = {"B": 0, "G1": 0, "G2": 0, "R": 0}

    for y in range(y0, y1):
        row_start = y * width + x0
        for x in range(x0, x1):
            pixel = frame[row_start + (x - x0)]
            if phase == "bggr":
                if y % 2 == 0:  # top row of 2x2 tile
                    if x % 2 == 0:
                        sums["B"] += pixel
                        counts["B"] += 1
                    else:
                        sums["G1"] += pixel
                        counts["G1"] += 1
                else:  # bottom row
                    if x % 2 == 0:
                        sums["G2"] += pixel
                        counts["G2"] += 1
                    else:
                        sums["R"] += pixel
                        counts["R"] += 1
            else:  # rggb
                if y % 2 == 0:
                    if x % 2 == 0:
                        sums["R"] += pixel
                        counts["R"] += 1
                    else:
                        sums["G1"] += pixel
                        counts["G1"] += 1
                else:
                    if x % 2 == 0:
                        sums["G2"] += pixel
                        counts["G2"] += 1
                    else:
                        sums["B"] += pixel
                        counts["B"] += 1

    # Compute means
    means = {ch: sums[ch] / counts[ch] if counts[ch] else 0.0 for ch in sums}
    return means

