#!/usr/bin/env python3
"""lynx-radio-snapshot: what Lynx's radios see, for her RADIO screen page (LNX-37-42).

Rose's backlog, group D "Radio visualization" (Gwyn, 2026-11-25). Read-only:
no scans of its own (Banshee's wifi-recon results are read from syslog), no
modem commands. Writes /run/lynx/radio.txt (RAM) about every 30 s:

    H|WI-FI                       header row
    W|SSID NOOBIA  2437 MHZ       text row: W white, G green, A amber, R red, M muted
    B|72|SIGNAL -51 DBM           bar row: 0-100 percent, then a label

    lynx-radio-snapshot --once | --loop [--every 30]
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import socket
import subprocess
import time

OUT = Path(os.environ.get("LYNX_RADIO_FILE", "/run/lynx/radio.txt"))
IW = "/usr/sbin/iw"
SYSLOG = Path("/var/log/lynx/messages")
NEXUS = ("192.168.100.106", 8080)
_prev = {"t": None, "rx": None, "tx": None}


def run(argv, timeout=5) -> str:
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def clean(text: str, n: int = 44) -> str:
    """Uppercase ASCII for the display font, no separators."""
    t = "".join(ch for ch in str(text) if 32 <= ord(ch) < 127).replace("|", "/")
    return t.upper()[:n]


def signal_percent(dbm: int) -> int:
    return max(0, min(100, int((dbm + 90) * 100 / 60)))   # -90 dBm = 0 %, -30 dBm = 100 %


def wifi(lines: list[str]) -> None:
    out = run([IW, "dev", "wlan0", "link"])
    lines.append("H|WI-FI")
    if not out or "Not connected" in out:
        lines.append("R|NOT CONNECTED")
        return
    ssid = re.search(r"SSID:\s*(.+)", out)
    freq = re.search(r"freq:\s*([\d.]+)", out)
    sig = re.search(r"signal:\s*(-?\d+)\s*dBm", out)
    rxr = re.search(r"rx bitrate:\s*([\d.]+)", out)
    txr = re.search(r"tx bitrate:\s*([\d.]+)", out)
    band = ""
    if freq:
        f = float(freq.group(1))
        band = "2.4 GHZ" if f < 3000 else ("5 GHZ" if f < 5900 else "6 GHZ")
    lines.append("W|" + clean(f"NETWORK {ssid.group(1).strip() if ssid else '?'}  {band}"))
    if sig:
        dbm = int(sig.group(1))
        lines.append(f"B|{signal_percent(dbm)}|" + clean(f"SIGNAL {dbm} DBM"))
    if rxr or txr:
        lines.append("W|" + clean(f"LINK RATE  DOWN {rxr.group(1) if rxr else '?'}  UP {txr.group(1) if txr else '?'} MBIT/S"))


def traffic(lines: list[str], now: float) -> None:
    rx = tx = None
    try:
        for line in Path("/proc/net/dev").read_text().splitlines():
            if line.strip().startswith("wlan0:"):
                cols = line.split(":", 1)[1].split()
                rx, tx = int(cols[0]), int(cols[8])
    except (OSError, ValueError, IndexError):
        pass
    lines.append("H|LIVE TRAFFIC (WLAN0)")
    if rx is None:
        lines.append("M|NO COUNTERS")
        return
    if _prev["t"] is not None and now > _prev["t"]:
        dt = now - _prev["t"]
        down = (rx - _prev["rx"]) * 8 / dt / 1000
        up = (tx - _prev["tx"]) * 8 / dt / 1000
        scale = lambda kbit: min(100, int(kbit / 50))       # 5 Mbit/s = full bar
        lines.append(f"B|{scale(down)}|" + clean(f"DOWN {down:.0f} KBIT/S"))
        lines.append(f"B|{scale(up)}|" + clean(f"UP {up:.0f} KBIT/S"))
    else:
        lines.append("M|MEASURING...")
    lines.append("M|" + clean(f"TOTAL  DOWN {rx // 1_000_000} MB  UP {tx // 1_000_000} MB"))
    _prev.update(t=now, rx=rx, tx=tx)


def topology(lines: list[str]) -> None:
    lines.append("H|NETWORK")
    route = run(["ip", "route"])
    gw = re.search(r"default via (\S+)", route)
    lines.append("W|" + clean(f"GATEWAY {gw.group(1) if gw else 'NONE'}"))
    try:
        with socket.create_connection(NEXUS, timeout=1.5):
            lines.append("G|" + clean(f"NEXUS {NEXUS[0]} REACHABLE"))
    except OSError:
        lines.append("R|" + clean(f"NEXUS {NEXUS[0]} UNREACHABLE"))
    neigh = [l.split() for l in run(["ip", "-4", "neigh", "show", "dev", "wlan0"]).splitlines() if l.strip()]
    alive = [n[0] for n in neigh if n and n[-1] in ("REACHABLE", "STALE", "DELAY", "PROBE")]
    lines.append("W|" + clean(f"DEVICES NEARBY ON THE LAN: {len(alive)}"))
    names = {NEXUS[0]: "NEXUS", gw.group(1) if gw else "": "GATEWAY"}
    for ip in sorted(alive, key=lambda a: [int(x) for x in a.split(".")])[:8]:
        lines.append("M|" + clean(f"  {ip}  {names.get(ip, '')}"))


def airspace(lines: list[str]) -> None:
    lines.append("H|WI-FI AROUND HER")
    last = ""
    try:
        with SYSLOG.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - 1_000_000))
            for raw in fh.read().decode("utf-8", "replace").splitlines():
                if "noobia-sense" in raw and "airspace scan" in raw:
                    last = raw
    except OSError:
        pass
    m = re.search(r"detected (\d+) networks; strongest is '([^']*)' on (\d+) MHz", last)
    if m:
        lines.append("W|" + clean(f"{m.group(1)} NETWORKS IN THE LAST SCAN"))
        lines.append("M|" + clean(f"STRONGEST {m.group(2)} ({m.group(3)} MHZ)"))
        stamp = last[:15]
        lines.append("M|" + clean(f"SCANNED {stamp}"))
    else:
        lines.append("M|NO RECENT SCAN (ASK HER TO RUN WIFI-RECON)")


def cellular(lines: list[str]) -> None:
    lines.append("H|CELLULAR (5G MODEM)")
    ccci = len(list(Path("/dev").glob("ccci_*")))
    ifaces = sorted(Path("/sys/class/net").glob("ccmni*"))
    up = sum(1 for i in ifaces if (i / "operstate").exists() and (i / "operstate").read_text().strip() == "up")
    lines.append(("W|" if ccci else "M|") + clean(f"MODEM CHANNELS {ccci}  DATA INTERFACES {len(ifaces)} ({up} UP)"))
    lines.append(("G|" if up else "A|") + ("REGISTERED / DATA ACTIVE" if up else "NO CARRIER: SIM NOT REGISTERED YET"))


def bluetooth(lines: list[str]) -> None:
    lines.append("H|BLUETOOTH")
    adapters = sorted(p.name for p in Path("/sys/class/bluetooth").glob("hci*")) \
        if Path("/sys/class/bluetooth").exists() else []
    lines.append(("G|" + clean("ADAPTER " + ", ".join(adapters))) if adapters else "M|NO ADAPTER UP")


def snapshot(now: float | None = None) -> str:
    now = now or time.time()
    lines = ["M|" + clean(time.strftime("UPDATED %H:%M:%S UTC", time.gmtime(now)))]
    for part in (wifi, lambda l: traffic(l, now), topology, airspace, cellular, bluetooth):
        try:
            part(lines)
        except Exception as exc:  # noqa: BLE001 - one broken source never blanks the page
            lines.append("R|" + clean(f"ERROR {type(exc).__name__}"))
    return "\n".join(lines) + "\n"


def write(text: str, path: Path = OUT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--every", type=float, default=30.0)
    args = ap.parse_args(argv)
    if args.loop:
        while True:
            write(snapshot())
            time.sleep(max(10.0, args.every))
    text = snapshot()
    write(text)
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
