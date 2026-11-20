"""Offline camera gate for the Lynx rear/front sensor capture requests.

This is a pure, offline planning helper. It parses a JSON request describing a
single sensor capture request and returns a concise allow/refuse decision with a
stable reason string. It encodes the current saved Lynx camera evidence:

* macro ``GC02M1`` at ``1600x1200 BA81`` and wide ``IMX355`` at
  ``3264x2448 BA81`` are the only routes that have produced recognizable
  RAM-only frames, so they are the only allowed routes -- and only when the
  request is explicitly optically verified.
* the main ``IMX890`` and front ``S5K3P9SP`` sensors use four-cell Bayer modes
  and remain untested, so they must not be streamed with an assumed single-cell
  ``BA81`` format.
* any other sensor, geometry, or pixel format is refused.

The module is pure: it performs no file, network, process, or hardware access.
The caller-supplied ``optically_verified`` field is a planning assertion, not
proof from a trusted receipt. Never use this result alone to authorize a live
camera route, stream, or module load.
Invalid inputs never raise from the public entry points; they classify as a
refused decision with a stable reason string.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Mapping, Optional

ALLOW = "allow"
REFUSE = "refuse"

DECISIONS = (ALLOW, REFUSE)

# (sensor, width, height, pixel_format) -> allow reason. Only these exact routes
# have produced recognizable RAM-only frames on the Lynx.
ALLOWED_ROUTES = {
    ("GC02M1", 1600, 1200, "BA81"): (
        "verified macro GC02M1 route (1600x1200 BA81, recognized RAM-only frames)"
    ),
    ("IMX355", 3264, 2448, "BA81"): (
        "verified IMX355 wide route (3264x2448 BA81, recognized RAM-only frames)"
    ),
}

# Sensors that are present on the Lynx but untested, using four-cell Bayer
# modes. They are hard-refused regardless of geometry, format, or the
# optically_verified flag.
REFUSED_SENSORS = {
    "IMX890": (
        "main IMX890 is untested and uses a four-cell Bayer mode; "
        "must not be streamed with an assumed single-cell BA81 format"
    ),
    "S5K3P9SP": (
        "front S5K3P9SP is untested and uses a four-cell Bayer mode; "
        "must not be streamed with an assumed single-cell BA81 format"
    ),
}

ALLOWED_SENSOR_NAMES = frozenset(sensor for sensor, _, _, _ in ALLOWED_ROUTES)

NOT_VERIFIED_REASON = (
    "optically_verified is not true; no recognizable optical scene has been "
    "validated for this route"
)
UNKNOWN_SENSOR_REASON = "sensor is not on the verified Lynx allow list"
UNKNOWN_ROUTE_REASON = (
    "no verified Lynx capture route for this sensor geometry/format pair"
)

# Fields every parsed camera request must carry.
_CORE_FIELDS = ("sensor", "width", "height", "pixel_format", "optically_verified")


@dataclass(frozen=True)
class CameraGateDecision:
    """Outcome of one camera gate evaluation."""

    decision: str
    reason: str
    sensor: str = ""
    width: int = 0
    height: int = 0
    pixel_format: str = ""
    optically_verified: bool = False

    def as_dict(self) -> dict:
        return {
            "decision": self.decision,
            "allowed": self.decision == ALLOW,
            "reason": self.reason,
            "sensor": self.sensor,
            "width": self.width,
            "height": self.height,
            "pixel_format": self.pixel_format,
            "optically_verified": self.optically_verified,
        }


def _plain_int(value: object) -> Optional[int]:
    """Return the value as an int, or None when it is not a plain integer."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _refuse(reason: str, **echo) -> CameraGateDecision:
    return CameraGateDecision(REFUSE, reason, **echo)


def _echo(request: Mapping) -> dict:
    """Collect normalized echo fields that exist and are well-typed."""
    echo = {
        "sensor": request["sensor"].strip().upper()
        if isinstance(request.get("sensor"), str) else "",
        "pixel_format": request["pixel_format"].strip().upper()
        if isinstance(request.get("pixel_format"), str) else "",
        "optically_verified": request["optically_verified"]
        if isinstance(request.get("optically_verified"), bool) else False,
    }
    width = _plain_int(request.get("width"))
    height = _plain_int(request.get("height"))
    if width is not None:
        echo["width"] = width
    if height is not None:
        echo["height"] = height
    return echo


def evaluate_request(request: object) -> CameraGateDecision:
    """Classify one parsed camera capture request.

    ``request`` must be a mapping carrying ``sensor``, ``width``, ``height``,
    ``pixel_format`` (a string), and ``optically_verified`` (a boolean).
    Invalid inputs never raise; they classify as a refused decision with a
    stable reason string.
    """
    if not isinstance(request, Mapping):
        return _refuse("invalid request: expected a mapping")

    for field in _CORE_FIELDS:
        if field not in request:
            return _refuse(f"invalid request: missing field {field}")

    if not isinstance(request["sensor"], str) or not request["sensor"].strip():
        return _refuse("invalid request: sensor must be a non-empty string")
    if not isinstance(request["pixel_format"], str) \
            or not request["pixel_format"].strip():
        return _refuse("invalid request: pixel_format must be a non-empty string")
    width = _plain_int(request["width"])
    if width is None or width <= 0:
        return _refuse("invalid request: width must be a positive integer")
    height = _plain_int(request["height"])
    if height is None or height <= 0:
        return _refuse("invalid request: height must be a positive integer")
    if not isinstance(request["optically_verified"], bool):
        return _refuse(
            "invalid request: optically_verified must be a boolean"
        )

    echo = _echo(request)
    sensor = echo["sensor"]
    pixel_format = echo["pixel_format"]
    verified = request["optically_verified"]
    route = (sensor, width, height, pixel_format)

    # Hard block: untested four-cell Bayer sensors are never allowed.
    if sensor in REFUSED_SENSORS:
        return _refuse(REFUSED_SENSORS[sensor], **echo)

    # Unknown sensor: not one of the verified Lynx routes.
    if sensor not in ALLOWED_SENSOR_NAMES:
        return _refuse(UNKNOWN_SENSOR_REASON, **echo)

    # Known allow-list sensor, but not a verified geometry/format pair.
    if route not in ALLOWED_ROUTES:
        return _refuse(UNKNOWN_ROUTE_REASON, **echo)

    # Verified route; require explicit optical verification.
    if not verified:
        return _refuse(NOT_VERIFIED_REASON, **echo)

    return CameraGateDecision(
        ALLOW, ALLOWED_ROUTES[route], **echo
    )


def gate(raw: object) -> CameraGateDecision:
    """Parse a camera request and classify it.

    ``raw`` may be a JSON document (``str`` or ``bytes``) or an already-parsed
    mapping. Invalid JSON or non-object documents classify as refused decisions
    rather than raising.
    """
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="replace")
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except ValueError as exc:
            return _refuse(f"invalid request: malformed JSON ({exc.__class__.__name__})")
        if not isinstance(parsed, Mapping):
            return _refuse("invalid request: expected a JSON object")
        return evaluate_request(parsed)
    return evaluate_request(raw)


def main(argv=None) -> int:
    """Command-line entry point: read a request from argv or stdin, emit JSON."""
    import sys

    argv = list(sys.argv[1:] if argv is None else argv)
    if argv:
        raw = " ".join(argv)
    else:
        raw = sys.stdin.read()
    decision = gate(raw)
    print(json.dumps(decision.as_dict(), indent=2, sort_keys=True))
    return 0 if decision.decision == ALLOW else 1


if __name__ == "__main__":
    raise SystemExit(main())
