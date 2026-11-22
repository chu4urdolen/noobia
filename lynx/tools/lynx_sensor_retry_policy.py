"""Pure retry policy for the Lynx sensorhub/audio bootstrap gates.

The classifier mirrors the gate sequence of
``/noobia/lynx/tools/lynx-sensorhub-bootstrap.sh`` and the validity rules
of ``/noobia/lynx/tools/lynx_noob_runtime.py``:

* gauge device type must be 42495,
* gauge error flags must be zero,
* charge must be at least 25 percent,
* battery temperature must be below 35000 millidegrees Celsius,
* SoC temperature must be below 45000 millidegrees Celsius,
* below 50 percent the gauge current must be positive (charging).

``classify_retry_policy`` is pure: it performs no file, network, or
process access, and it never raises on bad inputs -- invalid inputs are
reported as a ``wait`` decision with a stable reason string.  Decisions:

* ``wait``          -- a gate fails or the input is invalid; try again later,
* ``already_ready`` -- audio and sensorhub are already up; nothing to do,
* ``attempt_start`` -- every gate passes and sensorhub is not up yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional

WAIT = "wait"
ALREADY_READY = "already_ready"
ATTEMPT_START = "attempt_start"

ACTIONS = (WAIT, ALREADY_READY, ATTEMPT_START)

GAUGE_DEVICE_TYPE = 42495
MIN_CHARGE_PERCENT = 25
CHARGING_CHECK_BELOW_PERCENT = 50
BATTERY_TEMP_LIMIT_MC = 35000
SOC_TEMP_LIMIT_MC = 45000

# Validity ranges taken from the lynx_noob_runtime.py gauge and SoC checks.
CAPACITY_RANGE = (0, 100)
BATTERY_TEMP_RANGE = (-20000, 80000)
CURRENT_RANGE = (-10000, 10000)
SOC_TEMP_RANGE = (-20000, 120000)

# Fields every parsed Lynx battery snapshot must carry.
_CORE_FIELDS = (
    "gauge_device_type",
    "capacity_percent",
    "temperature_millidegrees_celsius",
    "gauge_current_ma_signed",
    "capacity_error",
    "temperature_error",
    "current_error",
)


@dataclass(frozen=True)
class RetryDecision:
    """Outcome of one retry-policy evaluation."""

    action: str
    reason: str

    def as_dict(self) -> dict:
        return {"action": self.action, "reason": self.reason}


def _to_int(value: object) -> Optional[int]:
    """Return the value as an int, or None when it is not a plain integer."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _wait(reason: str) -> RetryDecision:
    return RetryDecision(WAIT, reason)


def _check_flags(health_ok: object, audio_ready: object,
                 sensorhub_ready: object) -> bool:
    return all(isinstance(flag, bool)
               for flag in (health_ok, audio_ready, sensorhub_ready))


def classify_retry_policy(snapshot: object, soc_temp_mc: object,
                          health_ok: bool, audio_ready: bool,
                          sensorhub_ready: bool, guards_off: bool = False) -> RetryDecision:
    """Classify one Lynx bootstrap retry round.

    ``snapshot`` is the parsed battery snapshot mapping
    (``/sys/bus/i2c/devices/7-0055/battery_snapshot`` key=value pairs as
    ints), ``soc_temp_mc`` the SoC thermal zone temperature in
    millidegrees Celsius, and the three flags describe the Lynx runtime:
    device health, audio stack readiness, and sensorhub readiness.
    Invalid inputs never raise; they classify as ``wait``.
    """
    if not _check_flags(health_ok, audio_ready, sensorhub_ready):
        return _wait("invalid flags: expected booleans")

    # The retry loop asks "is it already up?" before touching the gauge.
    if audio_ready and sensorhub_ready:
        return RetryDecision(ALREADY_READY, "audio and sensorhub already up")

    soc = _to_int(soc_temp_mc)
    if soc is None or not SOC_TEMP_RANGE[0] <= soc <= SOC_TEMP_RANGE[1]:
        return _wait("invalid SoC temperature")

    if not isinstance(snapshot, Mapping):
        return _wait("invalid snapshot: expected a mapping")

    values = {}
    for field in _CORE_FIELDS:
        if field not in snapshot:
            return _wait(f"invalid snapshot: missing field {field}")
        value = _to_int(snapshot[field])
        if value is None:
            return _wait(f"invalid snapshot: {field} is not an integer")
        values[field] = value

    if not CAPACITY_RANGE[0] <= values["capacity_percent"] <= CAPACITY_RANGE[1]:
        return _wait("invalid snapshot: capacity_percent out of range")
    if not BATTERY_TEMP_RANGE[0] <= values["temperature_millidegrees_celsius"] \
            <= BATTERY_TEMP_RANGE[1]:
        return _wait("invalid snapshot: battery temperature out of range")
    if not CURRENT_RANGE[0] <= values["gauge_current_ma_signed"] <= CURRENT_RANGE[1]:
        return _wait("invalid snapshot: current out of range")

    # Any error flag present in the snapshot (including current_error and
    # voltage_error when the gauge reports them) must be zero.
    for field in sorted(f for f in snapshot if f.endswith("_error")):
        value = _to_int(snapshot[field])
        if value is None:
            return _wait(f"invalid snapshot: gauge error flag {field} not an integer")
        if value != 0:
            return _wait(f"wait: gauge error flag {field} is set")

    if values["gauge_device_type"] != GAUGE_DEVICE_TYPE:
        return _wait(f"gauge type is not {GAUGE_DEVICE_TYPE}")

    if not health_ok:
        return _wait("health not ok")

    charge = values["capacity_percent"]
    if guards_off:   # Tom 2026-11-22: charge/temperature limits off by switch
        return RetryDecision(ATTEMPT_START, "all bootstrap gates pass (guards off by switch)")
    if charge < MIN_CHARGE_PERCENT:
        return _wait(f"charge below {MIN_CHARGE_PERCENT} percent")

    if values["temperature_millidegrees_celsius"] >= BATTERY_TEMP_LIMIT_MC:
        return _wait(f"battery temperature at or above {BATTERY_TEMP_LIMIT_MC} mC")

    if soc >= SOC_TEMP_LIMIT_MC:
        return _wait(f"SoC temperature at or above {SOC_TEMP_LIMIT_MC} mC")

    if (charge < CHARGING_CHECK_BELOW_PERCENT
            and values["gauge_current_ma_signed"] <= 0):
        return _wait(f"below {CHARGING_CHECK_BELOW_PERCENT} percent and not charging")

    return RetryDecision(ATTEMPT_START, "all bootstrap gates pass")
