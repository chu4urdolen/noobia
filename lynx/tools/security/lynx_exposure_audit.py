#!/usr/bin/env python3
"""lynx-exposure-audit: what Lynx exposes to the network, read-only (LNX-78, LNX-63).

Rose's backlog, P0 "Firewall and exposed service audit" (Gwyn, 2026-11-25).
Run ON Lynx (python3 stdlib only). Changes nothing: it reads the kernel's
socket tables (/proc/net/tcp, tcp6, udp, udp6), maps each listening socket to
its program through /proc/<pid>/fd (one directory per process, no recursive
search), and compares what it finds with the expected services below.

    lynx-exposure-audit            JSON report
    lynx-exposure-audit --text     a short summary for people and agents

Exit status: 0 = nothing above "warn"; 1 = a "high" finding (an unexpected
listener, a protection missing); 2 = the audit itself failed.

Findings are observations, not proof of an attack (Rose's rule 8).
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import socket
import struct
import subprocess
import sys

PROC = Path(os.environ.get("LYNX_AUDIT_PROC", "/proc"))
SYS = Path(os.environ.get("LYNX_AUDIT_SYS", "/sys"))

# Expected listeners: port -> (name, program pattern, required cmdline options).
EXPECTED = {
    ("tcp", 2222): ("Alpine SSH (dropbear)", r"/dropbear$", ["-s", "-j", "-k"]),
    ("tcp", 22): ("early-boot rescue SSH (dropbear)", r"/dropbear$", ["-s", "-j", "-k"]),
    ("tcp", 4243): ("NRP daemon to Nexus (lynx-noobd)", r"lynx-noobd", ["--peer", "--nexus-key-file"]),
}
OPTION_MEANING = {"-s": "password logins disabled", "-j": "local port forwarding disabled",
                  "-k": "remote port forwarding disabled", "--peer": "only Nexus may connect",
                  "--nexus-key-file": "key-authenticated frames"}
TCP_LISTEN = "0A"
TCP_STATES = {"0A": "LISTEN"}


def _addr(hexaddr: str, v6: bool) -> str:
    ip, port = hexaddr.split(":")
    raw = bytes.fromhex(ip)
    if v6:
        raw = b"".join(struct.pack("<I", w) for w in struct.unpack(">4I", raw))
        text = str(ipaddress.IPv6Address(raw))
    else:
        text = socket.inet_ntoa(struct.pack("<I", int(ip, 16)))
    return f"{text}:{int(port, 16)}"


def sockets(proc: Path = PROC) -> list[dict]:
    """Listening TCP sockets and bound UDP sockets from the kernel tables."""
    found = []
    for proto in ("tcp", "tcp6", "udp", "udp6"):
        table = proc / "net" / proto
        try:
            lines = table.read_text().splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            cols = line.split()
            if len(cols) < 10:
                continue
            local, state, inode = cols[1], cols[3], cols[9]
            if proto.startswith("tcp") and state != TCP_LISTEN:
                continue
            addr = _addr(local, proto.endswith("6"))
            host, port = addr.rsplit(":", 1)
            if proto.startswith("udp") and int(port) == 0:
                continue
            found.append({"proto": proto, "address": host, "port": int(port), "inode": inode})
    return found


def owners(proc: Path = PROC) -> dict[str, dict]:
    """socket inode -> {pid, program, cmdline}, one /proc/<pid>/fd listing per process."""
    result = {}
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            cmd = (entry / "cmdline").read_bytes().split(b"\0")
            cmdline = [c.decode("utf-8", "replace") for c in cmd if c]
            fds = os.listdir(entry / "fd")
        except OSError:
            continue
        for fd in fds:
            try:
                target = os.readlink(entry / "fd" / fd)
            except OSError:
                continue
            m = re.fullmatch(r"socket:\[(\d+)\]", target)
            if m:
                result[m.group(1)] = {"pid": int(entry.name), "cmdline": cmdline}
    return result


def scope(address: str) -> str:
    ip = ipaddress.ip_address(address)
    if ip.is_unspecified:
        return "all interfaces"
    if ip.is_loopback:
        return "loopback"
    if ip.is_link_local:
        return "link-local"
    if ip.is_private:
        return "LAN"
    return "public"


def program_of(cmdline: list[str]) -> str:
    if not cmdline:
        return "?"
    if os.path.basename(cmdline[0]).startswith("python") and len(cmdline) > 1:
        return cmdline[1]
    return cmdline[0]


def read(path: Path, default: str = "") -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return default


def versions(run=subprocess.run, proc: Path = PROC) -> dict:
    out = {}
    for name, argv in (("dropbear", ["dropbear", "-V"]), ("python3", ["python3", "--version"])):
        if not shutil.which(argv[0]):
            continue
        try:
            r = run(argv, capture_output=True, text=True, timeout=5)
            text = (r.stdout + r.stderr).strip().splitlines()
            out[name] = text[0][:80] if text else "?"
        except (OSError, subprocess.SubprocessError):
            out[name] = "?"
    out["kernel"] = read(proc / "sys" / "kernel" / "osrelease", "?")
    return out


def audit(proc: Path = PROC, which=shutil.which, run=subprocess.run, sys_root: Path = SYS) -> dict:
    socks = sockets(proc)
    who = owners(proc)
    listeners, findings = [], []

    def finding(level, fid, text):
        findings.append({"level": level, "id": fid, "text": text})

    for s in socks:
        o = who.get(s["inode"], {"pid": None, "cmdline": []})
        prog = program_of(o["cmdline"])
        key = (s["proto"].rstrip("6"), s["port"])
        item = {"proto": s["proto"], "address": s["address"], "port": s["port"], "scope": scope(s["address"]),
                "pid": o["pid"], "program": prog}
        exp = EXPECTED.get(key)
        if exp and re.search(exp[1], prog):
            item["service"] = exp[0]
            missing = [opt for opt in exp[2] if opt not in o["cmdline"]]
            item["protections"] = [OPTION_MEANING[x] for x in exp[2] if x not in missing]
            for opt in missing:
                finding("high", f"missing-protection:{s['port']}",
                        f"{exp[0]} on port {s['port']} runs without {opt} ({OPTION_MEANING[opt]})")
        else:
            item["service"] = "UNEXPECTED"
            level = "info" if item["scope"] in ("loopback",) else "high"
            finding(level, f"unexpected-listener:{s['proto']}:{s['port']}",
                    f"unexpected {s['proto']} listener on {s['address']}:{s['port']} ({prog}, pid {o['pid']})")
        if item["scope"] in ("all interfaces", "public"):
            finding("warn", f"wide-bind:{s['port']}",
                    f"port {s['port']} listens on {item['scope']} ({s['address']}), not only the Noobia LAN")
        listeners.append(item)

    if any(l["port"] == 22 for l in listeners) and any(l["port"] == 2222 for l in listeners):
        finding("warn", "rescue-ssh-still-open",
                "the early-boot rescue SSH (port 22) still listens next to Alpine SSH (2222): "
                "a second door with the same key; close it after the hand-off, or keep it on purpose")
    fw = [t for t in ("nft", "iptables", "ip6tables") if which(t)]
    if not fw:
        finding("warn", "no-firewall", "no firewall tool installed (nft/iptables): nothing filters "
                "incoming traffic; every listener is reachable from the whole LAN (LNX-65)")
    if read(proc / "sys" / "net" / "ipv4" / "ip_forward", "0") != "0":
        finding("high", "ip-forward", "IPv4 forwarding is on: Lynx would route other devices' traffic")
    v6_off = read(proc / "sys" / "net" / "ipv6" / "conf" / "all" / "disable_ipv6", "1") == "1"
    lo_state = read(sys_root / "class" / "net" / "lo" / "operstate", "")
    if lo_state and lo_state.lower() not in ("up", "unknown"):
        finding("info", "loopback-down", f"loopback interface is {lo_state}: 127.0.0.1 services cannot run")
    high = sum(1 for f in findings if f["level"] == "high")
    return {"ok": high == 0, "listeners": listeners, "findings": findings,
            "firewall_tools": fw, "ipv6_enabled": not v6_off,
            "versions": versions(run, proc), "note": "observations, not proof of an attack (read-only audit)"}


def text_report(r: dict) -> str:
    lines = [f"Lynx exposure audit: {'OK' if r['ok'] else 'ATTENTION'} - "
             f"{len(r['listeners'])} listener(s), firewall: {', '.join(r['firewall_tools']) or 'none'}"]
    for l in r["listeners"]:
        prot = "; ".join(l.get("protections", [])) or "-"
        lines.append(f"  {l['proto']} {l['address']}:{l['port']} ({l['scope']}) {l['service']} [{l['program']}] {prot}")
    for f in r["findings"]:
        lines.append(f"  {f['level'].upper()}: {f['text']}")
    lines.append("  versions: " + ", ".join(f"{k} {v}" for k, v in r["versions"].items()))
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--text", action="store_true")
    args = ap.parse_args(argv)
    try:
        report = audit()
    except Exception as exc:  # noqa: BLE001 - say what failed, exit 2
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}))
        return 2
    print(text_report(report) if args.text else json.dumps(report, indent=1))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
