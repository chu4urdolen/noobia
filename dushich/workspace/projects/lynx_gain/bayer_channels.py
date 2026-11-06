"""Utilities for analysing BGGR Bayer frames.

This module provides a single public function :func:`bggr_channel_stats` that
takes a raw 8‑bit BGGR Bayer frame and returns per‑channel statistics.  The
function validates that the supplied frame dimensions are positive and even and
that the byte count matches ``width * height``.

The BGGR pattern is::

    B G
    G R

where the top‑left pixel is ``B``.  The two green pixels are distinguished by
their row position and are named ``G1`` (top row) and ``G2`` (bottom row).
The function returns a mapping of channel names to a dictionary containing
``count``, ``min``, ``max`` and ``mean`` for the channel.

Only the Python standard library is used; no external dependencies are
required.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

__all__ = ["bggr_channel_stats"]


@dataclass
class _ChannelStat:
    count: int = 0
    min: int | None = None
    max: int | None = None
    sum: int = 0

    def add(self, value: int) -> None:
        self.count += 1
        if self.min is None or value < self.min:
            self.min = value
        if self.max is None or value > self.max:
            self.max = value
        self.sum += value

    def mean(self) -> float:
        return self.sum / self.count if self.count else 0.0


def bggr_channel_stats(
    frame: bytes,
    width: int,
    height: int,
    phase: str = "bggr",
) -> Dict[str, Dict[str, float]]:
    """Return statistics for each channel in a Bayer frame.

    Parameters
    ----------
    frame:
        Raw frame data as a bytes object.  The length must equal ``width *
        height``.
    width, height:
        Dimensions of the image.  Both must be positive even integers.

    Returns
    -------
    dict
        Mapping ``"B"``, ``"G1"``, ``"G2"``, ``"R"`` to a dictionary with
        keys ``"count"``, ``"min"``, ``"max"`` and ``"mean"``.
    """

    if width <= 0 or height <= 0:
        raise ValueError("width and height must be positive")
    if width % 2 or height % 2:
        raise ValueError("width and height must be even for BGGR")
    expected_len = width * height
    if len(frame) != expected_len:
        raise ValueError(f"frame size {len(frame)} does not match width*height {expected_len}")

    # Validate phase
    phase = phase.lower()
    if phase not in ("bggr", "rggb"):
        raise ValueError("phase must be 'bggr' or 'rggb'")

    stats: Dict[str, _ChannelStat] = {
        "B": _ChannelStat(),
        "G1": _ChannelStat(),
        "G2": _ChannelStat(),
        "R": _ChannelStat(),
    }

    idx = 0
    for y in range(height):
        for x in range(width):
            pixel = frame[idx]
            if phase == "bggr":
                # BGGR pattern: B G1 on top row, G2 R on bottom row
                if y % 2 == 0:  # top row
                    if x % 2 == 0:
                        stats["B"].add(pixel)
                    else:
                        stats["G1"].add(pixel)
                else:  # bottom row
                    if x % 2 == 0:
                        stats["G2"].add(pixel)
                    else:
                        stats["R"].add(pixel)
            else:  # rggb
                # RGGB pattern: R G1 on top row, G2 B on bottom row
                if y % 2 == 0:  # top row
                    if x % 2 == 0:
                        stats["R"].add(pixel)
                    else:
                        stats["G1"].add(pixel)
                else:  # bottom row
                    if x % 2 == 0:
                        stats["G2"].add(pixel)
                    else:
                        stats["B"].add(pixel)
            idx += 1

    result: Dict[str, Dict[str, float]] = {}
    for name, st in stats.items():
        result[name] = {
            "count": st.count,
            "min": st.min if st.min is not None else 0,
            "max": st.max if st.max is not None else 0,
            "mean": st.mean(),
        }
    return result

