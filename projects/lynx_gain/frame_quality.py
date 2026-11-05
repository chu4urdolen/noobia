"""Utility to compute simple statistics for a raw Bayer frame.

The :func:`frame_quality` function expects an 8‑bit raw Bayer image stored
contiguously in :class:`bytes`.  It performs lightweight sanity checks and
returns a dictionary of useful metrics that can be used to compare frames
without any image‑processing libraries.
"""

from __future__ import annotations

from math import isfinite
from typing import Dict

__all__ = ["frame_quality"]


def frame_quality(frame: bytes, width: int, height: int, black_level: int = 16) -> Dict[str, float]:
    """Return a dictionary of quality metrics for a Bayer frame.

    Parameters
    ----------
    frame:
        Raw 8‑bit pixel data.
    width, height:
        Image dimensions; must be positive integers.
    black_level:
        Reference black level; must be in ``0``‑``254``.

    Returns
    -------
    dict
        Keys:
        ``pixel_count`` (int), ``raw_mean`` (float), ``positive_mean`` (float),
        ``black_fraction`` (float), ``saturated_fraction`` (float),
        ``p50`` (int), ``p95`` (int).
    """

    # Basic validation
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be positive")
    expected_len = width * height
    if len(frame) != expected_len:
        raise ValueError("frame size does not match width*height")
    if not 0 <= black_level <= 254:
        raise ValueError("black_level must be in 0..254")
    if not isfinite(black_level):
        raise ValueError("black_level must be finite")

    pixel_count = expected_len
    total = sum(frame)
    raw_mean = total / pixel_count

    # Positive signal mean (values above black level)
    pos_total = sum(v - black_level if v > black_level else 0 for v in frame)
    positive_mean = pos_total / pixel_count

    # Fractions
    black_frac = sum(1 for v in frame if v <= black_level) / pixel_count
    sat_frac = sum(1 for v in frame if v >= 250) / pixel_count

    # Histogram for percentiles
    hist = [0] * 256
    for v in frame:
        hist[v] += 1
    cumulative = 0
    p50 = None
    p95 = None
    for val, count in enumerate(hist):
        cumulative += count
        if p50 is None and cumulative >= 0.5 * pixel_count:
            p50 = val
        if p95 is None and cumulative >= 0.95 * pixel_count:
            p95 = val
        if p50 is not None and p95 is not None:
            break
    assert p50 is not None and p95 is not None
    return {
        "pixel_count": pixel_count,
        "raw_mean": raw_mean,
        "positive_mean": positive_mean,
        "black_fraction": black_frac,
        "saturated_fraction": sat_frac,
        "p50": p50,
        "p95": p95,
    }

