#!/usr/bin/env python3
"""S7 network sense for Lynx: neighbor devices on LAN.

Sampled sense. Data source: ``ip neigh`` (or /proc/net/arp).
Monitors neighbors on wlan0.

Events:
- New device reachable -> NOOBIA P1 network device.seen ip=... mac=...
- Device lost/failed   -> NOOBIA P3 network device.lost ip=...
- every 15 samples:    NOOBIA P0 network status.sample count=...
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from lynx_senses_lib import (  # noqa: E402
    SenseUnavailable,
    base_result,
    emit_line,
    failure,
    finish,
    import_sense,
    load_state,
    now_ts,
    save_state,
    state_path,
)

NETWORK_SAMPLE_EVERY = 15


def read_neighbors() -> dict[str, str]:
    """Returns mapping of ip -> mac for reachable/valid neighbors."""
    res = subprocess.run(["ip", "neigh"], capture_output=True, text=True, timeout=5, check=True)
    devices = {}
    for line in res.stdout.splitlines():
        parts = line.strip().split()
        if len(parts) >= 4 and "lladdr" in parts:
            ip = parts[0]
            mac_idx = parts.index("lladdr") + 1
            if mac_idx < len(parts):
                mac = parts[mac_idx]
                state = parts[-1]
                if state in ("REACHABLE", "STALE", "DELAY"):
                    devices[ip] = mac
    return devices


def run(dry_run: bool = False, state_file: str | None = None,
        reader=None, now: int | None = None) -> tuple[dict, int]:
    t = int(now if now is not None else now_ts())
    try:
        sense = import_sense()
    except SenseUnavailable as exc:
        return failure("network", exc)

    try:
        current_devices = (reader or read_neighbors)()
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return failure("network", exc)

    path = state_path("network", state_file)
    state = load_state(path)
    emitted: list[str] = []
    samples = int(state.get("samples", 0)) + 1
    prev_devices = state.get("devices")

    if prev_devices is None:
        # First sample: baseline only
        pass
    else:
        # Check for newly seen devices
        for ip, mac in current_devices.items():
            if ip not in prev_devices:
                line = emit_line(
                    sense,
                    1,
                    "network",
                    "device.seen",
                    fields={"ip": ip, "mac": mac},
                    text=f"Network device seen: {ip} ({mac})",
                    dry_run=dry_run,
                )
                emitted.append(line)
        # Check for lost devices
        for ip in prev_devices:
            if ip not in current_devices:
                line = emit_line(
                    sense,
                    1,
                    "network",
                    "device.lost",
                    fields={"ip": ip},
                    text=f"Network device lost: {ip}",
                    dry_run=dry_run,
                )
                emitted.append(line)

    if samples % NETWORK_SAMPLE_EVERY == 0:
        line = emit_line(
            sense,
            0,
            "network",
            "status.sample",
            fields={"count": len(current_devices)},
            text=f"Network neighbor count={len(current_devices)}",
            dry_run=dry_run,
        )
        emitted.append(line)

    new_state = {
        "samples": samples,
        "devices": current_devices,
        "last_ts": t,
    }
    if not dry_run:
        save_state(path, new_state)

    result = base_result("network", emitted=emitted, dry_run=dry_run)
    result.update({
        "devices_count": len(current_devices),
        "samples": samples,
    })
    return result, 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    res, code = run(dry_run=args.dry_run)
    return finish(res, code)


if __name__ == "__main__":
    main()
