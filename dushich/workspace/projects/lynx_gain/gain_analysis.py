"""Gain mapping for Lynx GC02M1.

The sensor expects raw gain values in the range 1024-12288. The V4L2
interface provides a gain value in the range 64-768. The relationship is
linear and can be expressed by a scale factor of 16:

    raw_gain = v4l2_gain * 16

This module provides a single helper function ``gain_mapper`` that performs
the conversion and validates the input range.
"""

from __future__ import annotations
import struct

# Public API of this module.  ``pack_stagger_ae`` is added alongside
# ``gain_mapper``.
__all__ = ["gain_mapper", "pack_stagger_ae"]

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


def _validate_int(value: int, name: str, lo: int, hi: int) -> None:
    """Internal helper to validate an integer range.

    Parameters
    ----------
    value:
        The value to validate.
    name:
        Human‑readable name for the error message.
    lo, hi:
        Inclusive lower and upper bounds.
    """
    # ``bool`` is a subclass of ``int`` so we need to reject it explicitly.
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be an integer, got {type(value).__name__}")
    if not (lo <= value <= hi):
        raise ValueError(
            f"{name} {value} out of range [{lo}, {hi}]"
        )


def pack_stagger_ae(exposure_lines: int, raw_gain: int) -> bytes:
    """Return a 52‑byte representation of the ``mtk_hdr_ae`` struct.

    The struct layout is defined as 13 little‑endian 32‑bit words:

    * Five words for exposure: ``le_exposure`` followed by four zeros.
    * Five words for gain: ``le_gain`` followed by four zeros.
    * One word for actions (zero).
    * One word for subsample_tags (zero).
    * One signed 32‑bit word for ``req_id`` (zero).

    Parameters
    ----------
    exposure_lines:
        Exposure value, must be an integer in the inclusive range
        ``1005``‑``3000``.
    raw_gain:
        Raw gain value, must be an integer in the inclusive range
        ``1024``‑``12288``.

    Returns
    -------
    bytes
        A 52‑byte sequence representing the struct.

    Raises
    ------
    ValueError
        If either argument is not an integer or is out of range.
    """
    _validate_int(exposure_lines, "exposure_lines", 1005, 3000)
    _validate_int(raw_gain, "raw_gain", 1024, 12288)

    # Build the list of 13 unsigned 32‑bit values.  ``struct.pack`` with the
    # ``<`` little‑endian format will produce the exact byte order required.
    values = [
        exposure_lines, 0, 0, 0, 0,  # exposure union
        raw_gain, 0, 0, 0, 0,  # gain union
        0,  # actions
        0,  # subsample_tags
        0,  # req_id signed i32 zero
    ]
    # ``I`` is unsigned 32‑bit; the value is zero for the last field, so
    # using unsigned is fine.
    return struct.pack("<13I", *values)

