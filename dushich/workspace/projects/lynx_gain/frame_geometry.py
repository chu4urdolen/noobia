"""Utility to compute buffer geometry for camera frames.

The :func:`geometry_for` function validates a sensor/mode pair and calculates
the number of bytes required for a raw image buffer including a 24‑byte
header.  It is deliberately minimal and uses only the standard library.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

__all__ = ["geometry_for"]


# Known sensor specifications – width and height in pixels.
_SENSOR_SPECS = {
    4: (1600, 1200),  # sensor4
    0: (4096, 3072),  # sensor0
    1: (2320, 1744),  # sensor1
    2: (3264, 2448),  # sensor2
}

_MAX_ALLOCATION = 32 * 1024 * 1024  # 32 MiB


def geometry_for(sensor: int, width: int, height: int, bytes_per_pixel: int = 1) -> Dict[str, int]:
    """Return a dictionary describing the geometry of a camera frame.

    Parameters
    ----------
    sensor:
        An integer identifying the camera sensor. Only the values defined in
        :data:`_SENSOR_SPECS` are accepted.
    width, height:
        The pixel dimensions of the frame. They must match the expected
        dimensions for the given sensor.
    bytes_per_pixel:
        Number of bytes per pixel (1 or 2). 2‑byte frames are used for 10‑bit
        raw data stored as little‑endian words.

    Returns
    -------
    dict
        Keys:
        ``sensor``, ``width``, ``height``, ``bytes_per_pixel``, ``image_bytes``
        ``header_bytes`` (always 24), ``allocation_bytes``.

    Raises
    ------
    ValueError
        If the sensor is unknown, the dimensions do not match the sensor
        specification, ``bytes_per_pixel`` is not 1 or 2, or the calculated
        allocation exceeds :data:`_MAX_ALLOCATION`.
    """

    if bytes_per_pixel not in (1, 2):
        raise ValueError("bytes_per_pixel must be 1 or 2")

    # Compute allocation before validating sensor mapping to provide a clear
    # overflow error when the requested buffer is too large.
    image_bytes = width * height * bytes_per_pixel
    header_bytes = 24
    allocation_bytes = image_bytes + header_bytes
    if allocation_bytes > _MAX_ALLOCATION:
        raise ValueError("buffer allocation exceeds 32 MiB limit")

    # Validate sensor mapping.
    spec = _SENSOR_SPECS.get(sensor)
    if spec is None or spec != (width, height):
        raise ValueError("unknown sensor/mode pair or mismatched dimensions")

    return {
        "sensor": sensor,
        "width": width,
        "height": height,
        "bytes_per_pixel": bytes_per_pixel,
        "image_bytes": image_bytes,
        "header_bytes": header_bytes,
        "allocation_bytes": allocation_bytes,
    }

