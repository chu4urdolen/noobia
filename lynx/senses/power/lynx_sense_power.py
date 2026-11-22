#!/usr/bin/env python3
"""S4 power sense for Lynx (PLAN.md): battery and thermal state.

Sampled sense. Data source: ``/usr/local/bin/lynx-status`` (schema 2) -
``battery.capacity_percent``, ``battery.current_mA_signed``,
``thermal.max_mC``. Charging state is derived from the signed gauge
current (lynx-status has no charger field; convention: >= +50 mA
charging, <= -50 mA discharging, between: idle - a deadband against
gauge noise).

Events (Aigel warn/fail convention, defaults documented and configurable):
- capacity <= 15%          -> NOOBIA P1 power battery.critical cap=... state=...
  (re-arms at >= 20%; one event per critical episode)
- capacity <= 30% (not critical) -> NOOBIA P3 power battery.low cap=... state=...
  (re-arms at >= 35%)
- SoC max >= 42.0 C        -> NOOBIA P3 power thermal.hot soc_mc=...
  (re-arms at <= 38.0 C; lynx-status itself flags thermal_hot at 55 C)
- charging state change    -> NOOBIA P5 power charging.change from=... to=... current_mA=...
- every 15 samples: NOOBIA P0 power status.sample cap=... current_mA=... soc=...

Convention: the first sample after a boot (or state loss) only sets the
baseline (including the charging state) and never emits. If the fuel
gauge is unavailable (capacity null) the sense stays silent about
battery and says so in the JSON output - it never invents a level.

    python3 /usr/local/lib/noobia/senses/power/lynx_sense_power.py [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from lynx_senses_lib import (  # noqa: E402
    POWER_CHARGE_MA,
    POWER_CRITICAL_PCT,
    POWER_CRITICAL_REARM_PCT,
    POWER_LOW_PCT,
    POWER_LOW_REARM_PCT,
    POWER_SAMPLE_EVERY,
    POWER_THERMAL_HOT_mC,
    POWER_THERMAL_REARM_mC,
    SenseUnavailable,
    base_result,
    emit_line,
    failure,
    finish,
    import_sense,
    load_state,
    lynx_status,
    now_ts,
    save_state,
    state_path,
)


def charging_state(current_ma: int | None) -> str:
    if current_ma is None:
        return "unknown"
    if current_ma >= POWER_CHARGE_MA:
        return "charging"
    if current_ma <= -POWER_CHARGE_MA:
        return "discharging"
    return "idle"


TEMP_CHECK_S = 60
TEMP_DELTA_C = 5.0


def run(dry_run: bool = False, state_file: str | None = None,
        status=None, now: int | None = None) -> tuple[dict, int]:
    """One power sample. status is injectable for tests.
    Returns (result_dict, exit_code)."""
    t = int(now if now is not None else now_ts())
    try:
        sense = import_sense()
    except SenseUnavailable as exc:
        return failure("power", exc)

    try:
        status_data = (status or lynx_status)()
    except (OSError, LookupError) as exc:
        return failure("power", exc)

    battery = status_data.get("battery") or {}
    cap = battery.get("capacity_percent")
    current = battery.get("current_mA_signed")
    soc = (status_data.get("thermal") or {}).get("max_mC")
    soc_max = soc
    state_name = charging_state(current)

    path = state_path("power", state_file)
    state = load_state(path)
    emitted: list[str] = []
    samples = int(state.get("samples", 0)) + 1
    first = state.get("charging") is None

    if first:
        # Baseline only: a freshly booted Lynx is not a charging event.
        pass
    elif state_name != "unknown" and state_name != state.get("charging"):
        line = emit_line(
            sense, 1, "power", "charging.change",
            fields={"from": state.get("charging", "unknown"),
                    "to": state_name,
                    **({"current_ma": current} if current is not None else {})},
            text={"charging": "Lynx is now charging",
                  "discharging": "Lynx is off the charger and running on battery",
                  "idle": "Lynx power state changed to idle"}.get(state_name,
                    "Lynx power state changed"),
            dry_run=dry_run)
        emitted.append(line)
        state["charging"] = state_name

    # Battery level (honest: null capacity means "unknown", never a
    # number; with no reading the arming state is left untouched).
    if cap is not None and 0 <= cap <= 100:
        critical = cap <= POWER_CRITICAL_PCT
        low = (not critical) and cap <= POWER_LOW_PCT
        if critical and not state.get("critical_armed"):
            line = emit_line(
                sense, 1, "power", "battery.critical",
                fields={"cap": cap, "state": state_name},
                text=f"Lynx battery is critically low ({cap}%)",
                dry_run=dry_run)
            emitted.append(line)
            state["critical_armed"] = True
            state["low_armed"] = True  # critical covers the low warning
        if low and not state.get("low_armed"):
            line = emit_line(
                sense, 1, "power", "battery.low",
                fields={"cap": cap, "state": state_name},
                text=f"Lynx battery is getting low ({cap}%)",
                dry_run=dry_run)
            emitted.append(line)
            state["low_armed"] = True
        # Re-arm hysteresis, checked after any trigger this sample.
        if cap >= POWER_CRITICAL_REARM_PCT:
            state["critical_armed"] = False
        if cap >= POWER_LOW_REARM_PCT and not low:
            state["low_armed"] = False

    # Thermal (SoC max).
    if soc is not None and isinstance(soc, int):
        if soc >= POWER_THERMAL_HOT_mC:
            if not state.get("thermal_armed"):
                line = emit_line(
                    sense, 1, "power", "thermal.hot",
                    fields={"soc_mc": soc, "state": state_name},
                    text=f"Lynx SoC is warm ({soc / 1000:.1f} C)",
                    dry_run=dry_run)
                emitted.append(line)
                state["thermal_armed"] = True
        if soc <= POWER_THERMAL_REARM_mC:
            state["thermal_armed"] = False

    # Temperature change (Tom, 2026-11-22): checked at most once a minute;
    # reported when her BATTERY temperature differs by >= TEMP_DELTA_C from
    # the last REPORTED reading. The SoC reading spikes for seconds during
    # every camera look, which made her report "hot" every minute.
    bat_t = battery.get("temperature_mC")
    soc = bat_t if isinstance(bat_t, int) and bat_t > 0 else None
    if soc is not None and isinstance(soc, int):
        ref = state.get("temp_ref_mC")
        last_check = int(state.get("temp_check_t", 0))
        if ref is None:
            state["temp_ref_mC"] = soc
            state["temp_check_t"] = t
        elif t - last_check >= TEMP_CHECK_S:
            state["temp_check_t"] = t
            delta = (soc - int(ref)) / 1000.0
            if abs(delta) >= TEMP_DELTA_C:
                line = emit_line(
                    sense, 1, "power", "temp.change",
                    fields={"dir": "rose" if delta > 0 else "dropped",
                            "c": int(round(soc / 1000)), "delta": int(round(abs(delta))),
                            "prev": int(round(int(ref) / 1000)), "state": state_name},
                    text=f"Lynx temperature {'rose' if delta > 0 else 'dropped'} to {soc / 1000:.1f} C",
                    dry_run=dry_run)
                emitted.append(line)
                state["temp_ref_mC"] = soc

    soc = soc_max
    if state_name != "unknown":
        state["charging"] = state_name
    if samples % POWER_SAMPLE_EVERY == 0:
        fields = {}
        if cap is not None:
            fields["cap"] = cap
        if current is not None:
            fields["current_ma"] = current
        if soc is not None:
            fields["soc"] = soc
        line = emit_line(sense, 0, "power", "status.sample",
                         fields=fields, text="", dry_run=dry_run)
        emitted.append(line)

    state["samples"] = samples
    state["t"] = t
    state["last_cap"] = cap
    state["last_soc_mC"] = soc

    if not dry_run:
        save_state(path, state)
    return (base_result("power",
                        sampled={"capacity_percent": cap,
                                "current_mA_signed": current,
                                "soc_mC": soc,
                                "charging": state_name,
                                "gauge_ok": cap is not None and 0 <= cap <= 100},
                        emitted=emitted, state=state), 0)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true",
                        help="print would-be sense lines; never write state or syslog")
    parser.add_argument("--state-file", default=None,
                        help="state file (default: /var/lib/noobia/senses/power/state.json)")
    args = parser.parse_args(argv)
    try:
        result, code = run(dry_run=args.dry_run, state_file=args.state_file)
    except (OSError, LookupError, ValueError) as exc:
        result, code = failure("power", exc)
    return finish(result, code)


if __name__ == "__main__":
    sys.exit(main())
