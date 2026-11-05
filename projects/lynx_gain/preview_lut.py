"""Utility to generate a lookup table for raw Bayer values.

The function :func:`make_lut` returns a :class:`bytes` object of length 256
containing a mapping from an 8‑bit input value *v* to an adjusted output
value.  The mapping applies a black level offset, a linear gain, and a
gamma correction.

The mapping formula is::

    out = round(255 * ((clamp((v - black_level) * gain, 0, 255) / 255) ** (1 / gamma)))

The result is clamped to the byte range 0‑255.  Parameters are validated
before use:

* ``black_level`` – integer in the inclusive range ``0``‑``254``.
* ``gain`` – positive real number.
* ``gamma`` – positive real number.

The function is deliberately lightweight and depends only on the Python
standard library.
"""

from __future__ import annotations

from math import isfinite
from typing import Iterable

__all__ = ["make_lut"]


def _validate_params(black_level: int, gain: float, gamma: float) -> None:
    if not isinstance(black_level, int):
        raise TypeError("black_level must be an int")
    if not 0 <= black_level <= 254:
        raise ValueError("black_level must be between 0 and 254 inclusive")
    if not isfinite(gain) or gain <= 0:
        raise ValueError("gain must be a finite positive number")
    if not isfinite(gamma) or gamma <= 0:
        raise ValueError("gamma must be a finite positive number")


def make_lut(black_level: int = 16, gain: float = 1.0, gamma: float = 1.0) -> bytes:
    """Return a 256‑byte lookup table.

    Parameters
    ----------
    black_level:
        Offset applied before gain; must be in 0‑254.
    gain:
        Linear gain multiplier; must be >0.
    gamma:
        Gamma exponent; must be >0.

    Returns
    -------
    bytes
        A 256‑byte LUT where index ``i`` maps to the adjusted value.
    """

    _validate_params(black_level, gain, gamma)

    lut = bytearray(256)
    for v in range(256):
        # Apply black level and gain, clamp to [0,255]
        adjusted = (v - black_level) * gain
        if adjusted < 0:
            adjusted = 0.0
        elif adjusted > 255:
            adjusted = 255.0
        # Gamma correction
        if gamma != 1.0:
            adjusted = adjusted / 255.0
            adjusted = adjusted ** (1.0 / gamma)
            adjusted = adjusted * 255.0
        # Final round and clamp to byte
        out = int(round(adjusted))
        if out < 0:
            out = 0
        elif out > 255:
            out = 255
        lut[v] = out
    return bytes(lut)

