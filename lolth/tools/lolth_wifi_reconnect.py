#!/usr/bin/env python3
"""Keep the dedicated Wi-Fi adapter connected to Lolth's access point."""

import argparse
import os
from pathlib import Path
import subprocess
import time


ADAPTER = "wlx20e017103ffb"
PROFILE = "Lolth LAFVIN AP"
FAST_SECONDS = 3
SLOW_SECONDS = 10
RECENT_WINDOW = 60


def run_nmcli(*args: str, timeout: int = 8) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["nmcli", *args], capture_output=True, text=True,
                          timeout=timeout, check=False)


def adapter_status() -> tuple[str, str]:
    result = run_nmcli("-t", "-f", "DEVICE,STATE,CONNECTION", "device", "status")
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "NetworkManager query failed")
    for line in result.stdout.splitlines():
        device, state, profile = line.split(":", 2)
        if device == ADAPTER:
            return state, profile
    raise RuntimeError(f"adapter {ADAPTER} is missing")


def last_online_path() -> Path:
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return Path(runtime_dir) / "lolth-wifi-last-online"


def read_last_online(path: Path) -> float:
    try:
        return float(path.read_text(encoding="ascii"))
    except (OSError, ValueError):
        return 0.0


def check_once(path: Path, dry_run: bool = False) -> int:
    now = time.time()
    recent = 0 <= now - read_last_online(path) < RECENT_WINDOW
    try:
        state, current = adapter_status()
    except (RuntimeError, subprocess.TimeoutExpired):
        return FAST_SECONDS if recent else SLOW_SECONDS

    if state == "connected" and current == PROFILE:
        path.write_text(str(now), encoding="ascii")
        return FAST_SECONDS

    if state.startswith("connecting") and current == PROFILE:
        return FAST_SECONDS if recent else SLOW_SECONDS

    # Outside the recent window, leave reconnection to NetworkManager's
    # ordinary autoconnect policy. In particular, do not displace another AP.
    if not recent:
        return SLOW_SECONDS

    if not dry_run:
        try:
            result = run_nmcli("--wait", "8", "connection", "up", PROFILE,
                               "ifname", ADAPTER, timeout=12)
            if result.returncode == 0 and adapter_status() == ("connected", PROFILE):
                path.write_text(str(time.time()), encoding="ascii")
        except (RuntimeError, subprocess.TimeoutExpired):
            pass
    return FAST_SECONDS


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="make one check, then exit")
    parser.add_argument("--dry-run", action="store_true", help="do not change Wi-Fi")
    args = parser.parse_args()
    path = last_online_path()
    while True:
        delay = check_once(path, args.dry_run)
        if args.once:
            return
        time.sleep(delay)


if __name__ == "__main__":
    main()
