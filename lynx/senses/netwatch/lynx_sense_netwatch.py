#!/usr/bin/env python3
"""S12 netwatch sense for Lynx: how her network is shaped and how well it works.

Rose's backlog (Gwyn, 2026-11-25, picked up from Banshee):

- LNX-33 ``route.change``: default gateway, interface or her own address changed.
- LNX-31 ``topology.change``: she roamed to another access point, joined another
  network (SSID), or her subnet changed. (Single devices coming and going are
  S7 ``network device.seen/lost``.)
- LNX-35 ``quality.change``: the link to her gateway and to Nexus moved between
  good / fair / poor / down (two samples in a row before she believes it).
- LNX-49 diagnosis: a ``quality.change`` to poor or down says *why*, checked
  layer by layer: Wi-Fi link, address, gateway, Nexus.
- LNX-32 / LNX-17 ``anomaly``: the gateway's hardware address changed while its
  IP stayed (a classic sign of ARP spoofing, or a new router), one hardware
  address answering for several IPs including the gateway, her DNS servers
  changing, or a sudden crowd of new neighbours.

Read-only and light: ``ip``, ``iw``, /etc/resolv.conf, two pings to the gateway
and one TCP connect to Nexus per sample. Rule 8: anomalies are observations,
not proof of an attack. Rule 9: she only perceives, never reacts against anyone.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import socket
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from lynx_sense_kit import Event, run_sense  # noqa: E402
from lynx_senses_lib import finish  # noqa: E402

IFACE = "wlan0"
NEXUS = ("192.168.100.106", 8080)
RESOLV = Path("/etc/resolv.conf")
CONFIRM = 2                 # samples in a row before a quality change counts
NEIGHBOUR_CROWD = 10        # this many new neighbours in one sample is a crowd
QUALITY_ORDER = ["good", "fair", "poor", "down"]


def sh(argv, timeout=6.0) -> str:
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def ping(host: str, count: int = 2) -> tuple[float | None, int]:
    """(average rtt ms or None, loss %) with BusyBox ping."""
    out = sh(["ping", "-c", str(count), "-W", "1", "-q", host], timeout=count + 3)
    loss = re.search(r"(\d+)% packet loss", out)
    rtt = re.search(r"= [\d.]+/([\d.]+)/", out)
    return (float(rtt.group(1)) if rtt else None), (int(loss.group(1)) if loss else 100)


def tcp_ms(addr, timeout=2.0) -> float | None:
    t = time.monotonic()
    try:
        with socket.create_connection(addr, timeout=timeout):
            return round((time.monotonic() - t) * 1000, 1)
    except OSError:
        return None


def observe() -> dict:
    route = sh(["ip", "-4", "route", "show", "default"])
    m = re.search(r"default via (\S+) dev (\S+)", route)
    gw, dev = (m.group(1), m.group(2)) if m else (None, None)
    addr = re.search(r"inet (\S+)", sh(["ip", "-4", "addr", "show", IFACE]))
    link = sh(["iw", "dev", IFACE, "link"])
    bssid = re.search(r"Connected to ([0-9a-f:]{17})", link)
    ssid = re.search(r"SSID:\s*(.+)", link)
    neigh = {}
    for line in sh(["ip", "-4", "neigh", "show", "dev", IFACE]).splitlines():
        p = line.split()
        if "lladdr" in p and p[-1] in ("REACHABLE", "STALE", "DELAY", "PROBE", "PERMANENT"):
            neigh[p[0]] = p[p.index("lladdr") + 1].lower()
    try:
        dns = sorted(re.findall(r"^\s*nameserver\s+(\S+)", RESOLV.read_text(), re.M))
    except OSError:
        dns = []
    rtt, loss = ping(gw) if gw else (None, 100)
    return {"gateway": gw, "dev": dev, "addr": addr.group(1) if addr else None,
            "bssid": bssid.group(1) if bssid else None,
            "ssid": ssid.group(1).strip() if ssid else None,
            "neigh": neigh, "dns": dns, "gw_rtt": rtt, "gw_loss": loss,
            "nexus_ms": tcp_ms(NEXUS)}


def quality(obs: dict) -> str:
    if not obs["bssid"] or not obs["gateway"] or (obs["gw_loss"] >= 100 and obs["nexus_ms"] is None):
        return "down"
    rtt, loss, nx = obs["gw_rtt"], obs["gw_loss"], obs["nexus_ms"]
    if loss >= 50 or nx is None or (rtt or 0) > 300:
        return "poor"
    if loss > 0 or (rtt or 0) > 60 or nx > 200:
        return "fair"
    return "good"


def diagnose(obs: dict) -> str:
    """LNX-49: the first broken layer, in plain words."""
    if not obs["bssid"]:
        return "my Wi-Fi is not connected to any access point"
    if not obs["addr"]:
        return "Wi-Fi is up but I have no IP address (DHCP)"
    if not obs["gateway"]:
        return "I have an address but no default route"
    if obs["gw_loss"] >= 100:
        return f"my gateway {obs['gateway']} does not answer"
    if obs["nexus_ms"] is None:
        return f"the gateway answers but Nexus {NEXUS[0]}:{NEXUS[1]} does not"
    if obs["gw_loss"] > 0:
        return f"{obs['gw_loss']}% of my pings to the gateway are lost"
    return f"the gateway takes {obs['gw_rtt']} ms and Nexus {obs['nexus_ms']} ms to answer"


def detect(prev: dict, obs: dict, now: float):
    ev = []
    base = bool(prev)

    # LNX-33 routes.
    route = {"gateway": obs["gateway"], "dev": obs["dev"], "addr": obs["addr"]}
    if base and prev.get("route") != route:
        old = prev.get("route") or {}
        what = [f"{k} {old.get(k)} -> {v}" for k, v in route.items() if old.get(k) != v]
        ev.append(Event("route.change", {"gateway": obs["gateway"], "addr": obs["addr"], "dev": obs["dev"]},
                        "My route changed: " + "; ".join(what) + ".", priority=3))

    # LNX-31 topology: AP, network, subnet.
    subnet = obs["addr"].rsplit(".", 1)[0] if obs["addr"] else None
    if base and obs["bssid"] and prev.get("bssid") and obs["bssid"] != prev["bssid"]:
        kind = "network" if obs["ssid"] != prev.get("ssid") else "roam"
        txt = (f"I joined another Wi-Fi network: {prev.get('ssid')} -> {obs['ssid']}." if kind == "network"
               else f"I roamed to another access point of {obs['ssid']} ({obs['bssid']}).")
        ev.append(Event("topology.change", {"kind": kind, "bssid": obs["bssid"]}, txt, priority=5))
    if base and subnet and prev.get("subnet") and subnet != prev["subnet"]:
        ev.append(Event("topology.change", {"kind": "subnet", "subnet": subnet},
                        f"My network changed from {prev['subnet']}.x to {subnet}.x.", priority=3))

    # LNX-35 + LNX-49 quality, confirmed over CONFIRM samples.
    q = quality(obs)
    seen = prev.get("q_seen") or [q]
    seen = (seen + [q])[-CONFIRM:]
    believed = prev.get("quality")
    if base and len(seen) == CONFIRM and len(set(seen)) == 1 and q != believed and believed:
        worse = QUALITY_ORDER.index(q) > QUALITY_ORDER.index(believed)
        why = f" Why: {diagnose(obs)}." if q in ("poor", "down") else ""
        ev.append(Event("quality.change", {"quality": q, "was": believed,
                                           "gw_ms": obs["gw_rtt"], "nexus_ms": obs["nexus_ms"]},
                        f"My connection {'got worse' if worse else 'improved'}: {believed} -> {q}.{why}",
                        priority=3 if worse else 5))
        believed = q
    if not believed:
        believed = q

    # LNX-32 / LNX-17 anomalies.
    gw, neigh, old_neigh = obs["gateway"], obs["neigh"], prev.get("neigh") or {}
    if base and gw and gw == (prev.get("route") or {}).get("gateway") and gw in neigh and gw in old_neigh \
            and neigh[gw] != old_neigh[gw]:
        ev.append(Event("anomaly", {"kind": "gateway_mac", "gateway": gw, "mac": neigh[gw]},
                        f"My gateway {gw} suddenly has a different hardware address ({old_neigh[gw]} -> "
                        f"{neigh[gw]}). A new router does that, and so does ARP spoofing.",
                        cooldown_s=900, key="anomaly:gwmac", priority=3, journal=True))
    owners = {}
    for ip, mac in neigh.items():
        owners.setdefault(mac, []).append(ip)
    for mac, ips in owners.items():
        if gw in ips and len(ips) > 1:
            ev.append(Event("anomaly", {"kind": "arp_conflict", "mac": mac, "count": len(ips)},
                            f"One device ({mac}) answers for my gateway and {len(ips) - 1} other "
                            f"address(es): {', '.join(sorted(ips))[:120]}.",
                            cooldown_s=1800, key="anomaly:arp", priority=3, journal=True))
    if base and prev.get("dns") is not None and obs["dns"] and obs["dns"] != prev["dns"]:
        ev.append(Event("anomaly", {"kind": "dns_change", "dns": ",".join(obs["dns"])[:32]},
                        f"My DNS servers changed: {', '.join(prev['dns'])} -> {', '.join(obs['dns'])}.",
                        cooldown_s=600, key="anomaly:dns", priority=3, journal=True))
    new = set(neigh) - set(old_neigh)
    if base and old_neigh and len(new) >= NEIGHBOUR_CROWD:
        ev.append(Event("anomaly", {"kind": "neighbour_crowd", "count": len(new)},
                        f"{len(new)} new devices appeared on my network at once.",
                        cooldown_s=900, key="anomaly:crowd", priority=3, journal=True))

    state = {"route": route, "bssid": obs["bssid"], "ssid": obs["ssid"], "subnet": subnet,
             "quality": believed, "q_seen": seen, "neigh": neigh, "dns": obs["dns"], "t": now}
    return ev, state


def run(dry_run: bool = False, state_file: str | None = None, now=None, sense_mod=None,
        observer=None, journal_path=None):
    return run_sense("netwatch", observer or observe, detect, dry_run=dry_run,
                     state_file=state_file, now=now, sense_mod=sense_mod, journal_path=journal_path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    return finish(*run(dry_run=args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
