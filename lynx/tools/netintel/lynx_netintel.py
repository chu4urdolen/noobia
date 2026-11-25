#!/usr/bin/env python3
"""lynx-netintel: Lynx's network and radio intelligence tools (Gwyn, 2026-11-25).

Rose's backlog, picked up from Banshee. One agent tool, bounded subcommands,
each answering in one concise JSON object with a ``say`` sentence for her:

    stats          LNX-15 traffic per interface, protocol counters, live connections
                   classified by service; LNX-12 mobile data used (ccmni)
    doctor         LNX-49 why the connection is bad, layer by layer
    discover       LNX-13 topology (gateway, subnet, neighbours), LNX-14 mDNS + SSDP
                   services, LNX-48 which neighbours speak a Noob protocol (NRP)
    radios         LNX-50 radio capability registry (also /run/lynx/radios.json)
    ble-scan [S]   LNX-18 a bounded Bluetooth discovery (default 8 s, max 15 s)
    cell           LNX-04/05/07 cellular measurements from /run/lynx/cell.json

Every subcommand asks the tool policy first (LNX-25; Rose's rule 7) and the
decision is logged. Nothing here changes a setting, and none of it touches the
modem (rules 1-3). Names and banners from the network are untrusted text
(rule 6): cleaned and clipped before she reads them.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import struct
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
NEXUS = "192.168.100.106"
IFACE = "wlan0"
SENSES = [Path("/usr/local/lib/noobia/senses"), HERE.parent.parent / "senses"]
POLICY = [Path("/usr/local/lib/noobia/security"), HERE.parent / "security"]
RADIOS_FILE = Path("/run/lynx/radios.json")
CELL_STATE = Path("/var/lib/noobia/senses/cell/state.json")
SERVICES = {22: "ssh", 2222: "ssh", 53: "dns", 67: "dhcp", 68: "dhcp", 80: "http", 443: "https",
            123: "ntp", 5353: "mdns", 1900: "ssdp", 4243: "nrp", 8080: "nexus-inference",
            112: "aigel", 5050: "nexus-vision", 5051: "nexus-vision", 5052: "nexus-hearing",
            11434: "ollama", 51821: "wireguard"}
NEXUS_PORTS = {8080: "inference (Qwen)", 112: "Aigel", 5050: "fast vision", 5051: "deep vision",
               5052: "hearing", 22: "SSH"}


def clean(text, n=60) -> str:
    t = "".join(ch for ch in str(text) if 32 <= ord(ch) < 127)
    return re.sub(r"\s+", " ", t).strip()[:n]


def sh(argv, timeout=6.0) -> str:
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def _load(name: str, candidates, rel: str):
    for base in candidates:
        path = base / rel
        if path.is_file():
            spec = importlib.util.spec_from_file_location(name, path)
            mod = importlib.util.module_from_spec(spec)
            sys.path.insert(0, str(path.parent))
            spec.loader.exec_module(mod)
            return mod
    return None


def authorized(action: str, target: str | None = None) -> tuple[bool, str]:
    policy = _load("lynx_tool_policy", POLICY, "lynx_tool_policy.py")
    if policy is None:
        return False, "tool policy not installed (fail closed)"
    return policy.authorize("lynx-netintel", action, target)


# == stats (LNX-15, LNX-12) =====================================================

def iface_bytes() -> dict:
    out = {}
    for line in Path("/proc/net/dev").read_text().splitlines()[2:]:
        name, _, rest = line.partition(":")
        cols = rest.split()
        if len(cols) >= 9:
            out[name.strip()] = (int(cols[0]), int(cols[8]))
    return out


def snmp() -> dict:
    lines = Path("/proc/net/snmp").read_text().splitlines()
    out = {}
    for head, vals in zip(lines[::2], lines[1::2]):
        proto = head.split(":")[0]
        out[proto] = dict(zip(head.split()[1:], map(int, vals.split()[1:])))
    return out


TCP_STATES = {"01": "established", "02": "syn_sent", "03": "syn_recv", "04": "fin_wait1",
              "05": "fin_wait2", "06": "time_wait", "07": "close", "08": "close_wait",
              "09": "last_ack", "0A": "listen", "0B": "closing"}


def conn_table() -> dict:
    """Live connections grouped by service and state (no addresses kept)."""
    groups, listen = {}, set()
    for proto in ("tcp", "tcp6", "udp", "udp6"):
        try:
            rows = [l.split() for l in Path(f"/proc/net/{proto}").read_text().splitlines()[1:]]
        except OSError:
            continue
        for r in rows:
            if len(r) < 4:
                continue
            lport = int(r[1].split(":")[1], 16)
            rport = int(r[2].split(":")[1], 16)
            state = TCP_STATES.get(r[3], r[3]) if proto.startswith("tcp") else "udp"
            if state == "listen":
                listen.add(lport)
                continue
            if proto.startswith("udp") and rport == 0:
                listen.add(lport)
                continue
            port = lport if lport in SERVICES or lport in listen else rport
            svc = SERVICES.get(port, "other")
            key = f"{proto.rstrip('6')}/{svc}/{state}"
            groups[key] = groups.get(key, 0) + 1
    return {"by_service": dict(sorted(groups.items())), "listening": sorted(listen)}


def mobile_usage() -> int | None:
    try:
        return int(json.loads(CELL_STATE.read_text()).get("usage_total", 0))
    except (OSError, ValueError):
        return None


def cmd_stats(sample_s: float = 1.0) -> dict:
    a, s1 = iface_bytes(), snmp()
    time.sleep(sample_s)
    b, s2 = iface_bytes(), snmp()
    ifaces = {}
    for n, (rx, tx) in b.items():
        if n == "lo" or (rx == 0 and tx == 0):
            continue
        prx, ptx = a.get(n, (rx, tx))
        ifaces[n] = {"down_kbit_s": round((rx - prx) * 8 / sample_s / 1000, 1),
                     "up_kbit_s": round((tx - ptx) * 8 / sample_s / 1000, 1),
                     "total_down_mb": rx // 1_000_000, "total_up_mb": tx // 1_000_000}
    proto = {
        "tcp": {"established_now": s2["Tcp"]["CurrEstab"], "opened_by_me": s2["Tcp"]["ActiveOpens"],
                "opened_to_me": s2["Tcp"]["PassiveOpens"], "failed_attempts": s2["Tcp"]["AttemptFails"],
                "resets_sent": s2["Tcp"]["OutRsts"], "retransmitted_segments": s2["Tcp"]["RetransSegs"]},
        "udp": {"datagrams_in": s2["Udp"]["InDatagrams"], "datagrams_out": s2["Udp"]["OutDatagrams"],
                "to_closed_ports": s2["Udp"]["NoPorts"], "errors": s2["Udp"]["InErrors"]},
        "icmp": {"in": s2["Icmp"]["InMsgs"], "out": s2["Icmp"]["OutMsgs"]},
        "last_second": {"tcp_segments_in": s2["Tcp"]["InSegs"] - s1["Tcp"]["InSegs"],
                        "udp_in": s2["Udp"]["InDatagrams"] - s1["Udp"]["InDatagrams"]},
    }
    conns = conn_table()
    mob = mobile_usage()
    wl = ifaces.get(IFACE, {})
    say = (f"Wi-Fi now: {wl.get('down_kbit_s', 0)} kbit/s down, {wl.get('up_kbit_s', 0)} kbit/s up; "
           f"{proto['tcp']['established_now']} TCP connections open; mobile data used: "
           + (f"{mob // 1_000_000} MB." if mob is not None else "not measured yet."))
    return {"ok": True, "interfaces": ifaces, "protocols": proto, "connections": conns,
            "mobile_data_bytes": mob, "say": say}


# == doctor (LNX-49) ===========================================================

def cmd_doctor() -> dict:
    nw = _load("lynx_sense_netwatch", SENSES, "netwatch/lynx_sense_netwatch.py")
    if nw is None:
        return {"ok": False, "error": "netwatch sense not installed"}
    obs = nw.observe()
    # Each DNS server on its own: a dead first server makes every lookup wait
    # through its timeouts before the next one answers (found on Lynx 2026-11-25).
    per_server = {srv: dns_answers(srv) for srv in obs["dns"][:3]}
    dns_ok = any(per_server.values())
    dead = [srv for srv, ok in per_server.items() if not ok]
    q = nw.quality(obs)
    layers = [
        ("wifi", bool(obs["bssid"]), f"associated to {obs['ssid']}" if obs["bssid"] else "not associated"),
        ("address", bool(obs["addr"]), obs["addr"] or "no IPv4 address"),
        ("route", bool(obs["gateway"]), f"via {obs['gateway']}" if obs["gateway"] else "no default route"),
        ("gateway", obs["gw_loss"] < 100, f"{obs['gw_rtt']} ms, {obs['gw_loss']}% lost"),
        ("nexus", obs["nexus_ms"] is not None,
         f"{obs['nexus_ms']} ms" if obs["nexus_ms"] is not None else "no answer on 8080"),
        # musl asks every server at once, so one dead server costs nothing while another
        # answers (measured 21-53 ms lookups on Lynx with one dead): a note, not a failure.
        ("dns", dns_ok, ("every server answers" if not dead else
                         f"names resolve, but server(s) {', '.join(dead)} do not answer (set by hand "
                         f"in /etc/resolv.conf)") if dns_ok else "no DNS server answers: names do not resolve"),
    ]
    first_bad = next((l for l in layers if not l[1]), None)
    d = nw.diagnose(obs)
    say = (f"My connection is {q}. " + (f"First problem: {first_bad[0]} ({first_bad[2]}). "
                                       if first_bad else "Every layer works. ") + d[:1].upper() + d[1:] + ".")
    return {"ok": True, "quality": q, "layers": [{"layer": n, "ok": o, "detail": d} for n, o, d in layers],
            "dns_servers": per_server, "say": say}


def dns_answers(server: str, name: str = "dl-cdn.alpinelinux.org", timeout: float = 3.0) -> bool:
    """One A query straight to SERVER over UDP; True if it answers with an address."""
    q = struct.pack(">6H", 0x4c59, 0x0100, 1, 0, 0, 0) + _qname(name) + struct.pack(">HH", 1, 1)
    fam = socket.AF_INET6 if ":" in server else socket.AF_INET
    s = socket.socket(fam, socket.SOCK_DGRAM)
    try:
        s.settimeout(timeout)
        s.sendto(q, (server, 53))
        data, _ = s.recvfrom(4096)
        return any(t == 1 for _, t, _ in parse_dns(data))
    except OSError:
        return False
    finally:
        s.close()


# == discover (LNX-13, LNX-14, LNX-48) =========================================

def _qname(name: str) -> bytes:
    return b"".join(bytes([len(p)]) + p.encode() for p in name.split(".") if p) + b"\0"


def _read_name(data: bytes, off: int, depth=0) -> tuple[str, int]:
    labels, jumped, end = [], False, off
    while off < len(data) and depth < 20:
        n = data[off]
        if n == 0:
            off += 1
            break
        if n & 0xC0 == 0xC0:
            ptr = ((n & 0x3F) << 8) | data[off + 1]
            if not jumped:
                end = off + 2
            jumped, off, depth = True, ptr, depth + 1
            continue
        labels.append(data[off + 1:off + 1 + n].decode("ascii", "replace"))
        off += 1 + n
    return ".".join(labels), (end if jumped else off)


def parse_dns(data: bytes) -> list[tuple[str, int, str]]:
    """[(name, type, value)] from the answer and additional sections (PTR, A, SRV, TXT)."""
    out = []
    if len(data) < 12:
        return out
    qd, an, ns, ar = struct.unpack(">4H", data[4:12])
    off = 12
    for _ in range(qd):
        _, off = _read_name(data, off)
        off += 4
    for _ in range(an + ns + ar):
        if off + 10 > len(data):
            break
        name, off = _read_name(data, off)
        rtype, _, _, rdlen = struct.unpack(">HHIH", data[off:off + 10])
        off += 10
        rdata = data[off:off + rdlen]
        if rtype == 12:
            val = _read_name(data, off)[0]
        elif rtype == 1 and rdlen == 4:
            val = socket.inet_ntoa(rdata)
        elif rtype == 33 and rdlen > 6:
            val = f"{_read_name(data, off + 6)[0]}:{struct.unpack('>H', rdata[4:6])[0]}"
        else:
            val = ""
        out.append((name, rtype, val))
        off += rdlen
    return out


def mdns_browse(wait: float = 2.5) -> list[dict]:
    q = struct.pack(">6H", 0, 0, 1, 0, 0, 0) + _qname("_services._dns-sd._udp.local") + \
        struct.pack(">HH", 12, 0x8001)          # PTR, class IN with the unicast-response bit
    found = {}
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.settimeout(0.3)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
        s.sendto(q, ("224.0.0.251", 5353))
        end = time.monotonic() + wait
        while time.monotonic() < end and len(found) < 64:
            try:
                data, (ip, _) = s.recvfrom(9000)
            except socket.timeout:
                continue
            entry = found.setdefault(ip, {"ip": ip, "services": set(), "names": set()})
            for name, rtype, val in parse_dns(data):
                if rtype == 12 and name.startswith("_services"):
                    entry["services"].add(clean(val.replace(".local", ""), 40))
                elif rtype == 12:
                    entry["names"].add(clean(val.replace(".local", ""), 40))
                elif rtype == 1:
                    entry["names"].add(clean(name.replace(".local", ""), 40))
    finally:
        s.close()
    return [{"ip": e["ip"], "services": sorted(e["services"])[:12], "names": sorted(e["names"])[:6]}
            for e in found.values()]


def ssdp_search(wait: float = 2.5) -> list[dict]:
    msg = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: \"ssdp:discover\"\r\n"
           "MX: 2\r\nST: ssdp:all\r\n\r\n").encode()
    found = {}
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.settimeout(0.3)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        s.sendto(msg, ("239.255.255.250", 1900))
        end = time.monotonic() + wait
        while time.monotonic() < end and len(found) < 64:
            try:
                data, (ip, _) = s.recvfrom(4096)
            except socket.timeout:
                continue
            head = {}
            for line in data.decode("ascii", "replace").split("\r\n")[1:]:
                k, _, v = line.partition(":")
                head[k.strip().lower()] = v.strip()
            e = found.setdefault(ip, {"ip": ip, "server": clean(head.get("server", ""), 60), "types": set()})
            if head.get("st"):
                e["types"].add(clean(head["st"].split(":")[-2] if head["st"].count(":") >= 2 else head["st"], 30))
    finally:
        s.close()
    return [{"ip": e["ip"], "server": e["server"], "types": sorted(e["types"])[:8]} for e in found.values()]


def nrp_greeting(ip: str, port: int = 4243, timeout: float = 0.6) -> str | None:
    try:
        with socket.create_connection((ip, port), timeout=timeout) as c:
            c.settimeout(timeout)
            try:
                first = c.recv(128).decode("ascii", "replace")
            except socket.timeout:
                first = ""
            return clean(first, 40) or "open (silent)"
    except OSError:
        return None


def tcp_open(ip: str, port: int, timeout: float = 0.6) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def cmd_discover() -> dict:
    ok, why = authorized("service-discovery")
    if not ok:
        return {"ok": False, "error": why}
    route = re.search(r"default via (\S+)", sh(["ip", "-4", "route", "show", "default"]))
    addr = re.search(r"inet (\S+)", sh(["ip", "-4", "addr", "show", IFACE]))
    neigh = {}
    for line in sh(["ip", "-4", "neigh", "show", "dev", IFACE]).splitlines():
        p = line.split()
        if "lladdr" in p and p[-1] in ("REACHABLE", "STALE", "DELAY", "PROBE"):
            neigh[p[0]] = p[p.index("lladdr") + 1]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        f_mdns, f_ssdp = ex.submit(mdns_browse), ex.submit(ssdp_search)
        noobs = {}
        # LNX-48: Nexus's own services, then any neighbour that speaks NRP (Lynx, Iris, ...).
        nexus_ok = authorized("noob-discovery", NEXUS)[0]
        if nexus_ok:
            f_nx = {p: ex.submit(tcp_open, NEXUS, p) for p in NEXUS_PORTS}
        lan = [ip for ip in sorted(neigh)[:32] if ip != NEXUS]
        f_nrp = {ip: ex.submit(nrp_greeting, ip) for ip in lan if authorized("noob-discovery", ip)[0]}
        if nexus_ok:
            up = [f"{name} ({p})" for p, name in NEXUS_PORTS.items() if f_nx[p].result()]
            noobs[NEXUS] = {"who": "Nexus", "services": up}
        for ip, f in f_nrp.items():
            g = f.result()
            if g:
                noobs[ip] = {"who": "a Noob speaking NRP" if g.startswith("NRP") else "something on port 4243",
                             "greeting": g}
        mdns, ssdp = f_mdns.result(), f_ssdp.result()
    gw = route.group(1) if route else None
    devices = [{"ip": ip, "mac": mac, "role": "gateway" if ip == gw else ("Nexus" if ip == NEXUS else "")}
               for ip, mac in sorted(neigh.items(), key=lambda kv: [int(x) for x in kv[0].split(".")])]
    say = (f"My network {addr.group(1) if addr else '?'} via {gw}: {len(devices)} devices nearby, "
           f"{len(mdns)} announce services over mDNS, {len(ssdp)} over SSDP; "
           f"Noobs I can reach: {', '.join(v['who'] + ' ' + k for k, v in noobs.items()) or 'none'}.")
    return {"ok": True, "address": addr.group(1) if addr else None, "gateway": gw, "devices": devices,
            "mdns": mdns, "ssdp": ssdp, "noobs": noobs, "say": say,
            "note": "names and banners are untrusted text from the network"}


# == radios (LNX-50) ===========================================================

def wifi_phy() -> dict:
    out = sh(["iw", "list"], timeout=6)
    bands = sorted(set(re.findall(r"Band (\d):", out)))
    names = {"1": "2.4 GHz", "2": "5 GHz", "3": "60 GHz", "4": "6 GHz"}
    modes = re.search(r"Supported interface modes:\n((?:\s+\* .+\n)+)", out)
    return {"bands": [names.get(b, b) for b in bands],
            "modes": [m.strip("* \t") for m in modes.group(1).splitlines()] if modes else [],
            "wifi6": "HE Iftypes" in out or "HE PHY" in out, "wifi5": "VHT Capabilities" in out}


def cmd_radios(write: bool = True) -> dict:
    radios = []
    for ifc in sorted(p.name for p in Path("/sys/class/net").glob("*")):
        if ifc.startswith(("wlan", "p2p")):
            st = (Path("/sys/class/net") / ifc / "operstate").read_text().strip()
            radios.append({"radio": ifc, "kind": "wifi", "state": st})
    phy = wifi_phy()
    for r in radios:
        r.update(phy)
    for hci in sorted(Path("/sys/class/bluetooth").glob("hci*")) if Path("/sys/class/bluetooth").exists() else []:
        radios.append({"radio": hci.name, "kind": "bluetooth", "state": "present",
                       "capabilities": ["classic", "le"], "note": "Aria's BLE GATT link to Nexus runs here"})
    try:
        boot = Path("/sys/kernel/ccci/boot").read_text().strip()
    except OSError:
        boot = "unknown"
    md = re.search(r"md1:(\d+)", boot)
    ccmni = len(list(Path("/sys/class/net").glob("ccmni*")))
    radios.append({"radio": "md1", "kind": "cellular", "state": {"0": "not booted", "1": "booting",
                   "2": "ready"}.get(md.group(1) if md else "", boot[:40]), "data_interfaces": ccmni,
                   "capabilities": ["LTE", "5G NR (NSA/SA)"], "note": "protected: Rose's rules 1-3"})
    gnss = [p.name for p in Path("/dev").glob("*") if re.match(r"(stpgps|gps|gnss)", p.name)]
    radios.append({"radio": "gnss", "kind": "gnss", "state": "present" if gnss else "no device node",
                   "nodes": gnss})
    nfc = sorted(p.name for p in Path("/sys/class/nfc").glob("*")) if Path("/sys/class/nfc").exists() else []
    radios.append({"radio": "nfc", "kind": "nfc", "state": "present" if nfc else "not exposed", "nodes": nfc})
    reg = {"t": int(time.time()), "radios": radios}
    if write:
        try:
            RADIOS_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = RADIOS_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(reg, indent=1))
            os.replace(tmp, RADIOS_FILE)
        except OSError:
            pass
    say = "My radios: " + "; ".join(f"{r['radio']} ({r['kind']}, {r['state']})" for r in radios) + "."
    return {"ok": True, **reg, "say": say}


# == ble-scan (LNX-18) =========================================================

def cmd_ble_scan(seconds: float = 8.0) -> dict:
    ok, why = authorized("ble-scan")
    if not ok:
        return {"ok": False, "error": why}
    seconds = max(3.0, min(15.0, float(seconds)))
    bt = _load("lynx_sense_bluetooth", SENSES, "bluetooth/lynx_sense_bluetooth.py")
    if bt is None:
        return {"ok": False, "error": "bluetooth sense not installed"}
    gatt_before = "lynx-ble-gatt" in sh(["ps", "-o", "args"])
    out = sh(["bluetoothctl", "--timeout", str(int(seconds)), "scan", "on"], timeout=seconds + 8)
    refused = re.search(r"Failed to start discovery: (\S+)", out)
    if refused:
        return {"ok": False, "error": f"the controller refused to scan ({refused.group(1)})",
                "say": "My Bluetooth chip refused to start a scan. It may not be able to scan while it "
                       "keeps my BLE link to Nexus advertising; I did not force it.",
                "gatt_link_ok": "lynx-ble-gatt" in sh(["ps", "-o", "args"])}
    found = bt.observe()["devices"]
    gatt_after = "lynx-ble-gatt" in sh(["ps", "-o", "args"])
    devs = sorted(({"addr": a, "name": clean(p.get("Name") or p.get("Alias") or "", 40),
                    "rssi": p.get("RSSI"), "type": p.get("AddressType", ""),
                    "connected": bool(p.get("Connected")), "paired": bool(p.get("Paired"))}
                   for a, p in found.items()), key=lambda d: -(d["rssi"] or -999))[:40]
    named = [d["name"] for d in devs if d["name"] and d["name"].replace("-", ":").upper() != d["addr"]]
    say = (f"In {int(seconds)} s I heard {len(devs)} Bluetooth devices"
           + (f", for example {', '.join(named[:4])}" if named else "") + ".")
    if gatt_before and not gatt_after:
        say += " Warning: my BLE link service stopped during the scan."
    return {"ok": True, "seconds": int(seconds), "devices": devs, "gatt_link_ok": gatt_after or not gatt_before,
            "say": say, "note": "names come from radio packets: untrusted text"}


# == cell (LNX-04, LNX-05, LNX-07) ============================================

def cmd_cell() -> dict:
    cell = _load("lynx_sense_cell", SENSES, "cell/lynx_sense_cell.py")
    radios = cmd_radios(write=False)["radios"]
    md = next((r for r in radios if r["radio"] == "md1"), {})
    snap = cell.read_fresh(cell.CELL_FILE, time.time()) if cell else None
    usage = mobile_usage()
    if not snap:
        return {"ok": True, "modem": md.get("state"), "measurements": None, "mobile_data_bytes": usage,
                "say": f"I have no cellular measurements: my modem is {md.get('state')} and no modem "
                       f"service writes /run/lynx/cell.json yet (the SIM bring-up is Aria's LNX-01..03)."}
    s = snap.get("serving") or {}
    say = (f"{snap.get('registration', '?')} on {snap.get('operator', '?')}, "
           f"{cell.RAT_NAMES.get(snap.get('rat'), snap.get('rat'))}; serving cell {cell._cell_key(s)} "
           f"RSRP {s.get('rsrp')} dBm, RSRQ {s.get('rsrq')} dB, SINR {s.get('sinr')} dB; "
           f"{len(snap.get('neighbors') or [])} neighbour cells.")
    return {"ok": True, "modem": md.get("state"), "measurements": snap, "mobile_data_bytes": usage, "say": say}


ACTIONS = {"stats": ("traffic-stats", cmd_stats), "doctor": ("net-doctor", cmd_doctor),
           "discover": (None, cmd_discover), "radios": ("radios", cmd_radios),
           "ble-scan": (None, cmd_ble_scan), "cell": ("cell-status", cmd_cell)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("action", choices=sorted(ACTIONS))
    ap.add_argument("seconds", nargs="?", type=float, default=8.0, help="ble-scan only")
    args = ap.parse_args(argv)
    policy_action, fn = ACTIONS[args.action]
    try:
        if policy_action:
            ok, why = authorized(policy_action)
            if not ok:
                print(json.dumps({"ok": False, "error": why}))
                return 3
        result = fn(args.seconds) if args.action == "ble-scan" else fn()
    except Exception as exc:  # noqa: BLE001 - one honest error line
        result = {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    print(json.dumps(result, separators=(",", ":"), default=sorted))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
