"""Gain mapping for Lynx GC02M1.

The sensor expects raw gain values in the range 1024-12288. The V4L2
interface provides a gain value in the range 64-768. The relationship is
linear and can be expressed by a scale factor of 16:

    raw_gain = v4l2_gain * 16

This module provides a single helper function ``gain_mapper`` that performs
the conversion and validates the input range.
"""

from __future__ import annotations

__all__ = ["gain_mapper"]

# Constants for the allowed ranges
V4L2_MIN = 64
V4L2_MAX = 768
RAW_MIN = V4L2_MIN * 16  # 1024
RAW_MAX = V4L2_MAX * 16  # 12288


def gain_mapper(v4l2_gain: int) -> int:
    """Convert a V4L2 gain value to the sensor's raw gain.

    Parameters
    ----------
    v4l2_gain:
        Integer gain value from the V4L2 interface. Must be in the
        inclusive range ``64``–``768``.

    Returns
    -------
    int
        The corresponding raw gain value (scaled by a factor of 16).

    Raises
    ------
    ValueError
        If ``v4l2_gain`` is not an integer or falls outside the valid
        range.
    """
    # Validate type first to provide a clear error message.
    if not isinstance(v4l2_gain, int):
        raise ValueError(
            f"V4L2 gain must be an integer, got {type(v4l2_gain).__name__}"
        )
    if not (V4L2_MIN <= v4l2_gain <= V4L2_MAX):
        raise ValueError(
            f"V4L2 gain {v4l2_gain} out of range [{V4L2_MIN}, {V4L2_MAX}]"
        )
    return v4l2_gain * 16

