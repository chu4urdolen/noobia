#!/usr/bin/env python3
"""S3 wifi sense for Lynx (PLAN.md): link state and weak-signal warnings.

Sampled sense. Data sources (both bounded, read-only):
- ``/usr/local/bin/lynx-status`` (schema 2): ``wifi.carrier`` / ``wifi.ipv4``.
- ``/usr/sbin/iw dev wlan0 link``: real signal in dBm when associated
  (``/proc/net/wireless`` reports -197 dBm unassociated, so it is not
  used; verified read-only on Lynx 2026-11-21).

Events:
- carrier up   ->  NOOBIA P1 wifi link.up iface=wlan0 ssid=...
- carrier down ->  NOOBIA P1 wifi link.down iface=wlan0
- signal <= -75 dBm (and previously fine) -> NOOBIA P3 wifi rssi.low
  signal=<dbm> iface=wlan0
  re-arms only when signal >= -70 dBm (hysteresis, one warning per low
  episode - Aigel collapses repeats anyway).
- every 15 samples: NOOBIA P0 wifi status.sample carrier=... signal=...
  (P0 never closes a chunk on its own: trigger.py triggers on p >= 1).

Convention: the first sample after a boot (or state loss) only sets the
baseline and never emits - a freshly booted Lynx with Wi-Fi up is not an
event. Honest failure: if lynx-status cannot be read, no event is
emitted and the result reports the error.

    python3 /usr/local/lib/noobia/senses/wifi/lynx_sense_wifi.py [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from lynx_senses_lib import (  # noqa: E402
    POWER_SAMPLE_EVERY,
    SenseUnavailable,
    WIFI_IFACE,
    WIFI_RSSI_LOW_DBM,
    WIFI_RSSI_REARM_DBM,
    base_result,
    emit_line,
    failure,
    finish,
    import_sense,
    iw_link,
    load_state,
    lynx_status,
    now_ts,
    save_state,
    state_path,
)


def run(dry_run: bool = False, state_file: str | None = None,
        status=None, link=None,
        now: int | None = None) -> tuple[dict, int]:
    """One wifi sample. status/link are injectable for tests.
    Returns (result_dict, exit_code)."""
    t = int(now if now is not None else now_ts())
    try:
        sense = import_sense()
    except SenseUnavailable as exc:
        return failure("wifi", exc)

    try:
        status_data = (status or lynx_status)()
        link_data = (link or iw_link)()
    except (OSError, LookupError) as exc:
        return failure("wifi", exc)

    carrier = bool(status_data.get("wifi", {}).get("carrier"))
    signal = link_data.get("signal_dbm")
    ssid = link_data.get("ssid")
    iface = link_data.get("iface") or WIFI_IFACE

    path = state_path("wifi", state_file)
    state = load_state(path)
    emitted: list[str] = []
    samples = int(state.get("samples", 0)) + 1

    if state.get("carrier") is None:
        # First sample: baseline only, never an event.
        state["carrier"] = carrier
    else:
        was_carrier = bool(state.get("carrier"))
        if was_carrier != carrier:
            if carrier:
                line = emit_line(
                    sense, 1, "wifi", "link.up",
                    fields={"iface": iface,
                            **({"ssid": ssid} if ssid else {})},
                    text="Wi-Fi is back", dry_run=dry_run)
            else:
                line = emit_line(
                    sense, 1, "wifi", "link.down",
                    fields={"iface": iface},
                    text="Wi-Fi went down", dry_run=dry_run)
            emitted.append(line)
            state["carrier"] = carrier
            state["rssi_armed"] = False

    # Weak-signal warning (only while associated with a readable signal).
    if carrier and signal is not None:
        armed = bool(state.get("rssi_armed"))
        if armed and signal >= WIFI_RSSI_REARM_DBM:
            state["rssi_armed"] = False  # hysteresis: link got better
        if not state.get("rssi_armed") and signal <= WIFI_RSSI_LOW_DBM:
            line = emit_line(
                sense, 1, "wifi", "rssi.low",
                fields={"signal": signal, "iface": iface},
                text=f"Wi-Fi signal is weak ({signal} dBm)",
                dry_run=dry_run)
            emitted.append(line)
            state["rssi_armed"] = True

    # P0 heartbeat: one status sample per POWER_SAMPLE_EVERY samples.
    if samples % POWER_SAMPLE_EVERY == 0:
        fields = {"carrier": int(carrier)}
        if signal is not None:
            fields["signal"] = signal
        line = emit_line(sense, 0, "wifi", "status.sample",
                         fields=fields, text="", dry_run=dry_run)
        emitted.append(line)

    state["samples"] = samples
    state["last_signal_dbm"] = signal
    state["last_carrier"] = carrier
    state["t"] = t

    if not dry_run:
        save_state(path, state)
    return (base_result("wifi", sampled={"carrier": carrier,
                                         "signal_dbm": signal,
                                         "ssid": ssid,
                                         "ipv4": status_data.get("wifi", {}).get("ipv4")},
                        emitted=emitted, state=state), 0)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true",
                        help="print would-be sense lines; never write state or syslog")
    parser.add_argument("--state-file", default=None,
                        help="state file (default: /var/lib/noobia/senses/wifi/state.json)")
    args = parser.parse_args(argv)
    try:
        result, code = run(dry_run=args.dry_run, state_file=args.state_file)
    except (OSError, LookupError, ValueError) as exc:
        result, code = failure("wifi", exc)
    return finish(result, code)


if __name__ == "__main__":
    sys.exit(main())
