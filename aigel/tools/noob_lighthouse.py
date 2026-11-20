#!/usr/bin/env python3
"""Noob Lighthouse - LAN presence and service beacon for the Noobia Wi-Fi.

Co-developed by Dushich and Banshee on Nexus.
A fast CLI/JSON status board that checks, in one glance, whether every known
inhabitant on `192.168.100.0/24` is reachable (ICMP ping) and whether their
Noob-facing TCP services are answering, plus the special `nexus_ready` state
(gateway + Nexus both online).
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

NOOBIA = os.environ.get("NOOBIA", "/noobia")

KNOWN_INHABITANTS = {
    "gateway": {"ip": "192.168.100.1", "role": "Noobia Wi-Fi Router", "tcp_ports": []},
    "nexus": {"ip": "192.168.100.106", "role": "Nexus (Aria, Banshee, Dushich)", "tcp_ports": [22, 8080, 48101]},
    "lynx": {"ip": "192.168.100.107", "role": "Lynx (Alpine / NRP/1)", "tcp_ports": [2222, 4243]},
    "argus": {"ip": "192.168.100.105", "role": "Argus (Historian)", "tcp_ports": [22, 47200, 47201]},
    "rose": {"ip": "192.168.100.7", "role": "Rose", "tcp_ports": [22, 47300, 47301]},
}

DEFAULT_ROSTER_FILE = NOOBIA + "/common/lighthouse_roster.json"


def load_roster(path: str | None = None) -> dict:
    """Load the inhabitant roster from the shared JSON config.

    Precedence: explicit ``path`` argument, the ``LIGHTHOUSE_ROSTER``
    environment variable, then ``DEFAULT_ROSTER_FILE``. Falls back to the
    built-in ``KNOWN_INHABITANTS`` table when the file is missing, unreadable,
    or malformed. Every entry needs at least an ``ip``.
    """
    candidate = path or os.environ.get("LIGHTHOUSE_ROSTER") or DEFAULT_ROSTER_FILE
    if candidate:
        try:
            data = json.loads(Path(candidate).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return dict(KNOWN_INHABITANTS)
        inhabitants = data.get("inhabitants", data) if isinstance(data, dict) else None
        if isinstance(inhabitants, dict) and inhabitants and all(
            isinstance(info, dict) and "ip" in info
            for info in inhabitants.values()
        ):
            return {name: dict(info) for name, info in inhabitants.items()}
    return dict(KNOWN_INHABITANTS)


def parse_ping_rtt(stdout: str) -> float | None:
    """Extract the average RTT in milliseconds from ping output, if present."""
    match = re.search(r"min/avg/max/mdev = [\d.]+/([\d.]+)", stdout)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def summarize_beacon_results(probes: dict[str, dict]) -> dict:
    """Summarize per-inhabitant probe results into a beacon status board.

    Parameters
    ----------
    probes:
        Mapping of inhabitant name -> probe record with keys ``ip``,
        ``role``, ``ping_ok`` (bool) and ``open_ports`` (list of ints).

    Returns
    -------
    dict
        ``online_count`` / ``total_count`` -- how many inhabitants are online.
        A node is online when ``ping_ok`` is True or any port is open.
        ``nexus_ready`` -- True when both ``gateway`` and ``nexus`` are online.
        ``online`` / ``offline`` -- sorted name lists.
        ``inhabitants`` -- the original probes mapping, unchanged.
    """
    online = {
        name
        for name, record in probes.items()
        if record.get("ping_ok") is True or bool(record.get("open_ports"))
    }
    offline = set(probes) - online
    return {
        "online_count": len(online),
        "total_count": len(probes),
        "nexus_ready": ("gateway" in online and "nexus" in online),
        "online": sorted(online),
        "offline": sorted(offline),
        "inhabitants": probes,
    }


def format_status_line(res: dict) -> str:
    """One compact human-readable status line for a beacon result."""
    rtt_bits = [
        f"{name}={int(res['inhabitants'][name]['rtt_ms'])}ms"
        for name in res["online"]
        if res["inhabitants"].get(name, {}).get("rtt_ms") is not None
    ]
    return (
        f"[noob-lighthouse] nexus_ready={res['nexus_ready']} "
        f"online={res['online_count']}/{res['total_count']} "
        f"online={','.join(res['online']) or '(none)'} "
        f"offline={','.join(res['offline']) or '(none)'}"
        + (f" rtt={','.join(rtt_bits)}" if rtt_bits else "")
    )


def _run_ping(ip: str) -> tuple[bool, float | None]:
    """Ping once; return (reachable, average RTT in ms or None)."""
    env = dict(os.environ)
    env["PATH"] = "/usr/sbin:/sbin:/usr/bin:/bin:" + env.get("PATH", "")
    try:
        proc = subprocess.run(
            ["ping", "-c", "1", "-W", "1", ip],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
            env=env,
        )
        return proc.returncode == 0, parse_ping_rtt(proc.stdout)
    except (OSError, subprocess.SubprocessError):
        return False, None


def _probe_ports(ip: str, ports: list[int], timeout: float) -> list[int]:
    open_ports: list[int] = []
    for port in ports:
        try:
            with socket.create_connection((ip, int(port)), timeout=timeout):
                open_ports.append(int(port))
        except OSError:
            continue
    return sorted(open_ports)


def probe_inhabitant(name: str, info: dict, timeout: float = 0.5) -> dict:
    """Ping one inhabitant and probe its Noob-facing TCP ports."""
    ip = info["ip"]
    ping_ok, rtt_ms = _run_ping(ip)
    return {
        "ip": ip,
        "role": info.get("role", ""),
        "ping_ok": ping_ok,
        "rtt_ms": rtt_ms,
        "open_ports": _probe_ports(ip, list(info.get("tcp_ports", [])), timeout),
    }


def probe_all(timeout: float = 0.5, roster: dict | None = None) -> dict:
    """Probe every known inhabitant in parallel and summarize the beacon.

    All inhabitants are probed concurrently via ``ThreadPoolExecutor`` so a
    healthy LAN returns well inside 1.5 seconds. The roster is loaded from
    the shared config file by default (see ``load_roster``).
    """
    roster = roster or load_roster()
    probes: dict[str, dict] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(roster))) as pool:
        futures = {
            pool.submit(probe_inhabitant, name, info, timeout): name
            for name, info in roster.items()
        }
        for future, name in futures.items():
            try:
                probes[name] = future.result(timeout=10)
            except (concurrent.futures.Error, Exception):
                probes[name] = {
                    "ip": roster[name]["ip"],
                    "role": roster[name].get("role", ""),
                    "ping_ok": False,
                    "rtt_ms": None,
                    "open_ports": [],
                }
    return summarize_beacon_results(probes)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print JSON beacon report")
    parser.add_argument("--once", action="store_true", help="Run one sweep and exit")
    parser.add_argument("--watch", action="store_true", help="Run periodic sweeps")
    parser.add_argument("--interval", type=int, default=15, help="Watch interval in seconds")
    parser.add_argument("--timeout", type=float, default=0.5, help="TCP probe timeout in seconds")
    args = parser.parse_args()

    while True:
        res = probe_all(timeout=args.timeout)
        if args.json:
            print(json.dumps(res, indent=2), flush=True)
        else:
            print(format_status_line(res), flush=True)
        if args.once or not args.watch:
            return 0 if res["nexus_ready"] else 1
        time.sleep(max(3, args.interval))


if __name__ == "__main__":
    sys.exit(main())
