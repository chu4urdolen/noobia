"""Utility to generate a sequence of ``media-ctl`` link commands.

Only the two sensor modes used in the Lynx capture flow are supported:
``4`` – the GC02M1 macro camera, and ``2`` – the IMX355 wide camera.
The function :func:`plan_route` takes the current mode and the target mode
and returns the list of ``media-ctl`` link descriptors that must be applied
in order.  The descriptor format is ``"[entity-id]"[port]:[direction]`` where
``[direction]`` is ``0`` to disable and ``5`` to enable.
"""

from __future__ import annotations

__all__ = ["plan_route"]


# Known entity IDs based on the Lynx /dev/media1 graph.
_SENSORS = {
    4: {"sensor": 45, "seninf": 27},
    2: {"sensor": 71, "seninf": 53},
}

_CAMSV = 615


def _link(entity: int, port: int, enable: bool) -> str:
    """Return a media-ctl link string for *entity* port.

    ``enable`` True -> ``[5]`` (enable), False -> ``[0]`` (disable).
    """

    flag = 5 if enable else 0
    return f"[{entity}]{port}:{flag}"


def plan_route(current: int, target: int) -> list[str]:
    """Return a list of media-ctl link descriptors to transition.

    Parameters
    ----------
    current, target:
        Integer identifiers for the sensor mode. Only ``4`` and ``2`` are
        accepted.

    Returns
    -------
    list[str]
        Ordered list of link commands.

    Raises
    ------
    ValueError
        If *current* or *target* is not 4 or 2, or if they are equal.
    """

    if current not in _SENSORS or target not in _SENSORS:
        raise ValueError("unsupported sensor id – only 4 and 2 are supported")
    if current == target:
        raise ValueError("current and target must differ")

    # Determine the direction of transition.
    if current == 4 and target == 2:
        # Disable links from sensor4 → seninf-1 and seninf-1 → CAMSV
        seq = [
            _link(_SENSORS[4]["seninf"], 1, False),  # seninf-1:1 disable
            _link(_SENSORS[4]["sensor"], 0, False),  # sensor4:0 disable
            _link(_SENSORS[2]["sensor"], 0, True),   # sensor2:0 enable
            _link(_SENSORS[2]["seninf"], 1, True),   # seninf-2:1 enable
            _link(_CAMSV, 0, True),                  # CAMSV-0 enable
        ]
    elif current == 2 and target == 4:
        seq = [
            _link(_CAMSV, 0, False),                # CAMSV-0 disable
            _link(_SENSORS[2]["seninf"], 1, False), # seninf-2:1 disable
            _link(_SENSORS[2]["sensor"], 0, False), # sensor2:0 disable
            _link(_SENSORS[4]["sensor"], 0, True),  # sensor4:0 enable
            _link(_SENSORS[4]["seninf"], 1, True),  # seninf-1:1 enable
        ]
    else:
        # Should never hit due to earlier checks.
        raise ValueError("unsupported transition")

    return seq

