#!/usr/bin/env python3
"""S10 security sense for Lynx: intrusion detection and attack resilience.

Implements Rose's Backlog (2026-11-25) security tasks:
- LNX-66 / LNX-98: Intrusion detection & unexpected listeners (security.intrusion.suspected)
- LNX-59 / LNX-95: Port scan perception (security.portscan.detected)
- LNX-67 / LNX-96: Authentication failure perception (security.authentication.failed)
- LNX-61 / LNX-97: TCP/UDP flood attack perception (security.flood.detected)
- LNX-72 / LNX-99: System file integrity monitoring (security.integrity.changed)
- LNX-74: Security incident journal (/var/log/lynx/security.jsonl)

Sampled sense. Reads read-only kernel tables (/proc/net/tcp, /proc/net/dev),
dropbear auth logs (/run/lynx/*.log), and system config hashes.
Changes nothing on Lynx hardware. Rose's Rule 8: Suspicious observations
are not proof of an attack. Rose's Rule 10: Security observations must be traceable.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import struct
import subprocess
import sys
import time

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

DEFAULT_PROC_DIR = "/proc"
DEFAULT_JOURNAL_FILE = "/var/log/lynx/security.jsonl"
DEFAULT_DROPBEAR_LOGS = [
    "/run/lynx/alpine-dropbear-2222.log",
    "/run/lynx/dropbear.log",
]
INTEGRITY_TARGETS = [
    "/etc/passwd",
    "/etc/shadow",
    "/root/.ssh/authorized_keys",
    "/etc/dropbear/authorized_keys",
    "/etc/inittab",
]

# Expected legitimate listeners (proto, port) -> name
EXPECTED_LISTENERS = {
    ("tcp", 22): "early-boot rescue SSH (dropbear)",
    ("tcp", 2222): "Alpine SSH (dropbear)",
    ("tcp", 4243): "NRP daemon to Nexus (lynx-noobd)",
}

TCP_LISTEN = "0A"
TCP_SYN_RECV = "03"
FLOOD_THRESHOLD_PPS = 1500
SECURITY_SAMPLE_EVERY = 15


def _hex_to_ip_port(hexaddr: str, v6: bool = False) -> tuple[str, int]:
    ip, port = hexaddr.split(":")
    raw = bytes.fromhex(ip)
    if v6:
        raw = b"".join(struct.pack("<I", w) for w in struct.unpack(">4I", raw))
        addr_str = str(ipaddress.IPv6Address(raw))
    else:
        addr_str = socket.inet_ntoa(struct.pack("<I", int(ip, 16)))
    return addr_str, int(port, 16)


def read_listening_sockets(proc_dir: str | Path = DEFAULT_PROC_DIR) -> list[dict]:
    """Parse /proc/net/tcp and /proc/net/tcp6 for listening sockets."""
    proc = Path(proc_dir)
    results = []
    # Gwyn 2026-11-25: a UDP socket that is connected, or bound to a port in the
    # kernel's ephemeral range, is a client (a DNS lookup, an mDNS query), not a
    # listener; reporting those raised false "intrusion.suspected" lines.
    try:
        lo, hi = map(int, (proc / "sys/net/ipv4/ip_local_port_range").read_text().split()[:2])
    except (OSError, ValueError):
        lo, hi = 32768, 60999
    for proto in ("tcp", "tcp6", "udp", "udp6"):
        table = proc / "net" / proto
        if not table.exists():
            continue
        try:
            lines = table.read_text().splitlines()[1:]
        except OSError:
            continue
        is_v6 = proto.endswith("6")
        for line in lines:
            cols = line.split()
            if len(cols) < 10:
                continue
            local, state, inode = cols[1], cols[3], cols[9]
            if proto.startswith("tcp") and state != TCP_LISTEN:
                continue
            try:
                ip, port = _hex_to_ip_port(local, is_v6)
                if proto.startswith("udp") and port == 0:
                    continue
                if proto.startswith("udp") and (lo <= port <= hi or
                                                not cols[2].split(":")[0].strip("0") == ""):
                    continue
                results.append({
                    "proto": "tcp" if proto.startswith("tcp") else "udp",
                    "ip": ip,
                    "port": port,
                    "inode": inode,
                })
            except Exception:
                continue
    return results


def check_syn_recv_probes(proc_dir: str | Path = DEFAULT_PROC_DIR) -> dict[str, int]:
    """Identify foreign IPs probing multiple ports simultaneously in SYN_RECV."""
    proc = Path(proc_dir)
    table = proc / "net" / "tcp"
    if not table.exists():
        return {}
    probes: dict[str, set[int]] = {}
    try:
        lines = table.read_text().splitlines()[1:]
        for line in lines:
            cols = line.split()
            if len(cols) < 10:
                continue
            local, remote, state = cols[1], cols[2], cols[3]
            if state == TCP_SYN_RECV:
                _, local_port = _hex_to_ip_port(local, False)
                remote_ip, _ = _hex_to_ip_port(remote, False)
                if remote_ip not in probes:
                    probes[remote_ip] = set()
                probes[remote_ip].add(local_port)
    except OSError:
        pass
    return {ip: len(ports) for ip, ports in probes.items() if len(ports) >= 3}


def read_network_rates(proc_dir: str | Path = DEFAULT_PROC_DIR) -> dict[str, dict]:
    """Read rx_packets and rx_bytes from /proc/net/dev."""
    proc = Path(proc_dir)
    dev_path = proc / "net" / "dev"
    if not dev_path.exists():
        return {}
    rates = {}
    try:
        lines = dev_path.read_text().splitlines()[2:]
        for line in lines:
            if ":" not in line:
                continue
            iface, stats = line.split(":", 1)
            iface = iface.strip()
            cols = stats.split()
            if len(cols) >= 8:
                rx_bytes = int(cols[0])
                rx_packets = int(cols[1])
                rates[iface] = {"rx_bytes": rx_bytes, "rx_packets": rx_packets}
    except (OSError, ValueError):
        pass
    return rates


def read_auth_failures(log_paths: list[str], offsets: dict[str, int]) -> tuple[list[dict], dict[str, int]]:
    """Scan dropbear log files for new authentication failures since last offset."""
    failures = []
    new_offsets = dict(offsets)
    fail_pattern = re.compile(
        r"(?:Bad password attempt|Login attempt for nonexistent user|Pubkey auth failed) "
        r"for '(?P<user>[^']+)' from (?P<ip>[0-9.]+):(?P<port>\d+)"
    )

    for path_str in log_paths:
        p = Path(path_str)
        if not p.exists():
            continue
        try:
            size = p.stat().st_size
            last_pos = offsets.get(path_str, 0)
            if size < last_pos:
                last_pos = 0  # Rotated
            with p.open("r", encoding="utf-8", errors="replace") as f:
                f.seek(last_pos)
                for line in f:
                    m = fail_pattern.search(line)
                    if m:
                        failures.append({
                            "service": "ssh",
                            "user": m.group("user"),
                            "ip": m.group("ip"),
                            "port": int(m.group("port")),
                            "line": line.strip()[:160],
                        })
                new_offsets[path_str] = f.tell()
        except OSError:
            continue

    return failures, new_offsets


def calculate_integrity_hashes(paths: list[str]) -> dict[str, str]:
    """Compute sha256 checksums of key system configuration files."""
    hashes = {}
    for p_str in paths:
        p = Path(p_str)
        if not p.exists():
            hashes[p_str] = "missing"
            continue
        try:
            h = hashlib.sha256(p.read_bytes()).hexdigest()
            hashes[p_str] = h
        except OSError:
            hashes[p_str] = "unreadable"
    return hashes


def record_incident_journal(journal_path: str, event: str, fields: dict, text: str) -> None:
    """Append structured security event to local append-only journal (LNX-74)."""
    p = Path(journal_path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": round(time.time(), 3),
            "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "event": event,
            "fields": fields,
            "text": text,
            "rule": "Rose Rule 10 (traceable)",
        }
        # Private (Gwyn 2026-11-25): create 0600 and tighten an older 0644 journal.
        fd = os.open(p, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            if os.fstat(fd).st_mode & 0o077:
                os.fchmod(fd, 0o600)
            f.write(json.dumps(record, sort_keys=True) + "\n")
    except OSError:
        pass


def run(
    dry_run: bool = False,
    state_file: str | None = None,
    proc_dir: str | Path = DEFAULT_PROC_DIR,
    journal_file: str = DEFAULT_JOURNAL_FILE,
    dropbear_logs: list[str] | None = None,
    now: int | None = None,
    socket_reader=None,
    rate_reader=None,
    auth_reader=None,
    hash_reader=None,
) -> tuple[dict, int]:
    t = int(now if now is not None else now_ts())
    try:
        sense = import_sense()
    except SenseUnavailable as exc:
        return failure("security", exc)

    if dropbear_logs is None:
        dropbear_logs = DEFAULT_DROPBEAR_LOGS

    path = state_path("security", state_file)
    state = load_state(path)
    emitted: list[str] = []
    samples = int(state.get("samples", 0)) + 1

    # 1. Check Listening Sockets (LNX-66 / LNX-98: Unexpected Listeners)
    current_listeners = (socket_reader or (lambda: read_listening_sockets(proc_dir)))()
    known_unexpected = set(state.get("unexpected_listeners", []))
    for listener in current_listeners:
        key = (listener["proto"], listener["port"])
        key_str = f"{listener['proto']}:{listener['port']}"
        if key not in EXPECTED_LISTENERS:
            if key_str not in known_unexpected:
                known_unexpected.add(key_str)
                line = emit_line(
                    sense,
                    20,
                    "security",
                    "intrusion.suspected",
                    fields={
                        "port": listener["port"],
                        "proto": listener["proto"],
                        "addr": listener["ip"],
                    },
                    text=f"Unexpected network listener detected on port {listener['port']}/{listener['proto']}",
                    dry_run=dry_run,
                )
                emitted.append(line)
                if not dry_run:
                    record_incident_journal(
                        journal_file,
                        "security.intrusion.suspected",
                        listener,
                        f"Unexpected network listener on {listener['ip']}:{listener['port']}/{listener['proto']}",
                    )

    # 2. Check SYN_RECV Port Scan Probes (LNX-59 / LNX-95)
    syn_probes = check_syn_recv_probes(proc_dir)
    for src_ip, count in syn_probes.items():
        line = emit_line(
            sense,
            20,
            "security",
            "portscan.detected",
            fields={"source_ip": src_ip, "port_count": count},
            text=f"Port scan detected from {src_ip} ({count} ports targeted)",
            dry_run=dry_run,
        )
        emitted.append(line)
        if not dry_run:
            record_incident_journal(
                journal_file,
                "security.portscan.detected",
                {"source_ip": src_ip, "port_count": count},
                f"Port scan probe detected from {src_ip} targeting {count} ports",
            )

    # 3. Check Authentication Failures (LNX-67 / LNX-96)
    prev_offsets = state.get("log_offsets", {})
    if auth_reader:
        new_auth_fails, new_offsets = auth_reader(dropbear_logs, prev_offsets)
    else:
        new_auth_fails, new_offsets = read_auth_failures(dropbear_logs, prev_offsets)

    if new_auth_fails:
        # Group by IP
        by_ip: dict[str, list[dict]] = {}
        for af in new_auth_fails:
            by_ip.setdefault(af["ip"], []).append(af)
        for ip, items in by_ip.items():
            user = items[0]["user"]
            attempts = len(items)
            line = emit_line(
                sense,
                20,
                "security",
                "authentication.failed",
                fields={"service": "ssh", "source_ip": ip, "attempts": attempts, "user": user},
                text=f"SSH authentication failure from {ip} ({attempts} attempts, user={user})",
                dry_run=dry_run,
            )
            emitted.append(line)
            if not dry_run:
                record_incident_journal(
                    journal_file,
                    "security.authentication.failed",
                    {"service": "ssh", "source_ip": ip, "attempts": attempts, "user": user},
                    f"Authentication failure on SSH service from {ip} ({attempts} attempts)",
                )

    # 4. Check Traffic Rates / Flood Surge (LNX-61 / LNX-97)
    rates_now = (rate_reader or (lambda: read_network_rates(proc_dir)))()
    prev_rates = state.get("rates", {})
    prev_ts = float(state.get("last_ts") or t)
    dt = max(t - prev_ts, 1.0)
    current_pps = 0

    if prev_rates:
        for iface, cur_stat in rates_now.items():
            if iface not in prev_rates:
                continue
            dpkt = cur_stat["rx_packets"] - prev_rates[iface]["rx_packets"]
            dbytes = cur_stat["rx_bytes"] - prev_rates[iface]["rx_bytes"]
            if dpkt > 0:
                pps = int(dpkt / dt)
                mbps = round((dbytes * 8) / (dt * 1_000_000), 2)
                if iface == "wlan0":
                    current_pps = pps
                if pps >= FLOOD_THRESHOLD_PPS:
                    line = emit_line(
                        sense,
                        20,
                        "security",
                        "flood.detected",
                        fields={"iface": iface, "pps": pps, "mbps": mbps},
                        text=f"High network traffic surge on {iface} ({pps} packets/sec, {mbps} Mbps)",
                        dry_run=dry_run,
                    )
                    emitted.append(line)
                    if not dry_run:
                        record_incident_journal(
                            journal_file,
                            "security.flood.detected",
                            {"iface": iface, "pps": pps, "mbps": mbps},
                            f"Traffic flood surge on {iface}: {pps} pps ({mbps} Mbps)",
                        )

    # 5. Check Integrity Hashes (LNX-72 / LNX-99)
    current_hashes = (hash_reader or (lambda: calculate_integrity_hashes(INTEGRITY_TARGETS)))()
    prev_hashes = state.get("hashes")
    if prev_hashes is None:
        # First sample sets baseline
        prev_hashes = current_hashes
    else:
        for path_checked, cur_h in current_hashes.items():
            old_h = prev_hashes.get(path_checked)
            if old_h is not None and old_h != cur_h and old_h != "missing":
                line = emit_line(
                    sense,
                    20,
                    "security",
                    "integrity.changed",
                    fields={"path": path_checked},
                    text=f"System file integrity change detected in {path_checked}",
                    dry_run=dry_run,
                )
                emitted.append(line)
                if not dry_run:
                    record_incident_journal(
                        journal_file,
                        "security.integrity.changed",
                        {"path": path_checked, "prev_hash": old_h[:8], "curr_hash": cur_h[:8]},
                        f"Integrity alteration detected in system configuration {path_checked}",
                    )

    # 6. Periodic Sample (P0)
    if samples % SECURITY_SAMPLE_EVERY == 0:
        line = emit_line(
            sense,
            0,
            "security",
            "status.sample",
            fields={
                "listeners": len(current_listeners),
                "pps": current_pps,
                "auth_fails": len(new_auth_fails),
            },
            text=f"Security status: {len(current_listeners)} listeners, {current_pps} pps, {len(new_auth_fails)} auth failures",
            dry_run=dry_run,
        )
        emitted.append(line)

    new_state = {
        "samples": samples,
        "last_ts": t,
        "unexpected_listeners": list(known_unexpected),
        "log_offsets": new_offsets,
        "rates": rates_now,
        "hashes": current_hashes,
    }

    if not dry_run:
        save_state(path, new_state)

    result = base_result("security", emitted=emitted, dry_run=dry_run)
    result.update({
        "listeners_count": len(current_listeners),
        "pps": current_pps,
        "new_auth_fails": len(new_auth_fails),
        "emitted_count": len(emitted),
    })
    return result, 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print without modifying state")
    args = parser.parse_args(argv)
    res, code = run(dry_run=args.dry_run)
    return finish(res, code)


if __name__ == "__main__":
    sys.exit(main())
