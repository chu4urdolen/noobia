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
import socket
import subprocess
import sys
import time

KNOWN_INHABITANTS = {
    "gateway": {"ip": "192.168.100.1", "role": "Noobia Wi-Fi Router", "tcp_ports": []},
    "nexus": {"ip": "192.168.100.106", "role": "Nexus (Aria, Banshee, Dushich)", "tcp_ports": [22, 8080, 48101]},
    "lynx": {"ip": "192.168.100.107", "role": "Lynx (Alpine / NRP/1)", "tcp_ports": [2222, 4243]},
    "argus": {"ip": "192.168.100.105", "role": "Argus (Historian)", "tcp_ports": [22, 47200, 47201]},
    "rose": {"ip": "192.168.100.7", "role": "Rose", "tcp_ports": [22, 47300, 47301]},
}


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


def _run_ping(ip: str) -> bool:
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
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


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
    return {
        "ip": ip,
        "role": info.get("role", ""),
        "ping_ok": _run_ping(ip),
        "open_ports": _probe_ports(ip, list(info.get("tcp_ports", [])), timeout),
    }


def probe_all(timeout: float = 0.5) -> dict:
    """Probe every known inhabitant in parallel and summarize the beacon.

    All five inhabitants are probed concurrently via ``ThreadPoolExecutor``
    so a healthy LAN returns well inside 1.5 seconds.
    """
    probes: dict[str, dict] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(KNOWN_INHABITANTS))) as pool:
        futures = {
            pool.submit(probe_inhabitant, name, info, timeout): name
            for name, info in KNOWN_INHABITANTS.items()
        }
        for future, name in futures.items():
            try:
                probes[name] = future.result(timeout=10)
            except (concurrent.futures.Error, Exception):
                probes[name] = {
                    "ip": KNOWN_INHABITANTS[name]["ip"],
                    "role": KNOWN_INHABITANTS[name].get("role", ""),
                    "ping_ok": False,
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
            print(
                f"[noob-lighthouse] nexus_ready={res['nexus_ready']} "
                f"online={res['online_count']}/{res['total_count']} "
                f"online={','.join(res['online']) or '-'} "
                f"offline={','.join(res['offline']) or '-'}",
                flush=True,
            )
        if args.once or not args.watch:
            return 0 if res["nexus_ready"] else 1
        time.sleep(max(3, args.interval))


if __name__ == "__main__":
    sys.exit(main())
