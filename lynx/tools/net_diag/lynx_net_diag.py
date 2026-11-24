#!/usr/bin/env python3
"""Lynx Autonomous Network Diagnostics Suite (Pwnphone Diagnostic Toolkit).

Subcommands:
  wifi-recon      Scan Wi-Fi airspace for SSIDs, BSSIDs, frequencies, and signal strengths (iw)
  lan-sweep       Discover live neighbors on the local subnet via ARP and ping (ip neigh)
  port-scan       Targeted lightweight port scan against an IP (nmap / socket probe)
  dns-audit       DNS latency, resolver check, and domain query benchmarking (dig)
  packet-sample   Sample and summarize N packets on the interface (tcpdump)
  traceroute      Hop-by-hop latency and route trace (traceroute / mtr)
  speed-check     Bandwidth / network throughput test (iperf3 / curl download timing)

Returns structured JSON for agent and sense consumption.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
from typing import Any


def run_cmd(args: list[str], timeout: float = 15) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "command timed out"
    except Exception as exc:
        return 1, "", str(exc)


# ----------------------------------------------------------------------
# 1. Wi-Fi Airspace Reconnaissance (iw)
# ----------------------------------------------------------------------
def wifi_recon(iface: str = "wlan0") -> dict[str, Any]:
    code, stdout, stderr = run_cmd(["iw", "dev", iface, "scan"], timeout=12)
    if code != 0 and not stdout:
        return {"ok": False, "error": stderr or "scan failed"}

    networks = []
    current: dict[str, Any] = {}
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("BSS "):
            if current and current.get("bssid"):
                networks.append(current)
            bssid_match = re.search(r"BSS ([0-9a-fA-F:]{17})", line)
            current = {
                "bssid": bssid_match.group(1).lower() if bssid_match else "unknown",
                "associated": "-- associated" in line,
                "ssid": "<hidden>",
                "freq_mhz": None,
                "signal_dbm": None,
                "security": "open",
            }
        elif line.startswith("freq:") and current:
            try:
                current["freq_mhz"] = float(line.split()[1])
            except ValueError:
                pass
        elif line.startswith("signal:") and current:
            try:
                current["signal_dbm"] = float(line.split()[1])
            except ValueError:
                pass
        elif line.startswith("SSID:") and current:
            current["ssid"] = line.split("SSID:", 1)[1].strip() or "<hidden>"
        elif ("RSN" in line or "WPA" in line) and current:
            current["security"] = "WPA2/WPA3"

    if current and current.get("bssid"):
        networks.append(current)

    # Sort by signal strength (strongest first)
    networks.sort(key=lambda n: n.get("signal_dbm") or -100, reverse=True)
    return {
        "ok": True,
        "iface": iface,
        "count": len(networks),
        "networks": networks,
    }


# ----------------------------------------------------------------------
# 2. LAN Neighbor Sweep (ARP / Neighbors)
# ----------------------------------------------------------------------
def lan_sweep(iface: str = "wlan0") -> dict[str, Any]:
    code, stdout, stderr = run_cmd(["ip", "-4", "neigh", "show", "dev", iface], timeout=5)
    neighbors = []
    for line in stdout.splitlines():
        parts = line.split()
        if len(parts) >= 4 and "lladdr" in parts:
            ip = parts[0]
            mac = parts[parts.index("lladdr") + 1]
            state = parts[-1]
            neighbors.append({
                "ip": ip,
                "mac": mac,
                "state": state,
                "is_gateway": ip.endswith(".1"),
            })

    return {
        "ok": True,
        "iface": iface,
        "count": len(neighbors),
        "neighbors": neighbors,
    }


# ----------------------------------------------------------------------
# 3. Port Scan (nmap / socket fallback)
# ----------------------------------------------------------------------
def port_scan(target: str, ports: str = "22,80,443,112,5050,8080,11434") -> dict[str, Any]:
    # Check if nmap exists
    nmap_path = "/usr/bin/nmap"
    if os.path.exists(nmap_path):
        code, stdout, stderr = run_cmd(
            [nmap_path, "-sT", "-T4", "--open", "-p", ports, "-Pn", target],
            timeout=15,
        )
        open_ports = []
        for line in stdout.splitlines():
            m = re.match(r"^(\d+)/(tcp|udp)\s+open\s+(\S+)", line.strip())
            if m:
                open_ports.append({
                    "port": int(m.group(1)),
                    "proto": m.group(2),
                    "service": m.group(3),
                })
        return {
            "ok": True,
            "target": target,
            "method": "nmap",
            "open_ports": open_ports,
        }

    # Lightweight socket probe fallback
    port_list = [int(p.strip()) for p in ports.split(",") if p.strip().isdigit()]
    open_ports = []
    for p in port_list:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.6)
            if s.connect_ex((target, p)) == 0:
                open_ports.append({"port": p, "proto": "tcp", "service": "unknown"})

    return {
        "ok": True,
        "target": target,
        "method": "socket",
        "open_ports": open_ports,
    }


# ----------------------------------------------------------------------
# 4. DNS Audit & Latency Benchmark
# ----------------------------------------------------------------------
def dns_audit(domain: str = "google.com", server: str | None = None) -> dict[str, Any]:
    args = ["dig", "+stats", "+time=2", "+tries=1", domain]
    if server:
        args.append(f"@{server}")

    code, stdout, stderr = run_cmd(args, timeout=5)
    query_time_ms = None
    server_used = server
    status = "UNKNOWN"

    for line in stdout.splitlines():
        if "Query time:" in line:
            m = re.search(r"Query time:\s+(\d+)\s+msec", line)
            if m:
                query_time_ms = int(m.group(1))
        elif "SERVER:" in line:
            m = re.search(r"SERVER:\s+([0-9a-fA-F.:]+)", line)
            if m:
                server_used = m.group(1)
        elif "status:" in line:
            m = re.search(r"status:\s+(\w+)", line)
            if m:
                status = m.group(1)

    return {
        "ok": code == 0,
        "domain": domain,
        "server": server_used,
        "status": status,
        "query_time_ms": query_time_ms,
    }


# ----------------------------------------------------------------------
# 5. Packet Sampling (tcpdump summary)
# ----------------------------------------------------------------------
def packet_sample(iface: str = "wlan0", count: int = 15) -> dict[str, Any]:
    code, stdout, stderr = run_cmd(
        ["tcpdump", "-i", iface, "-n", "-c", str(count), "-q"],
        timeout=10,
    )
    packets = []
    for line in stdout.splitlines():
        line = line.strip()
        if line:
            packets.append(line[:120])

    return {
        "ok": code == 0 or len(packets) > 0,
        "iface": iface,
        "captured": len(packets),
        "summary": packets,
    }


# ----------------------------------------------------------------------
# 6. Traceroute Route Audit
# ----------------------------------------------------------------------
def route_trace(target: str = "8.8.8.8", max_hops: int = 8) -> dict[str, Any]:
    code, stdout, stderr = run_cmd(
        ["traceroute", "-n", "-q", "1", "-w", "1", "-m", str(max_hops), target],
        timeout=12,
    )
    hops = []
    for line in stdout.splitlines():
        line = line.strip()
        m = re.match(r"^(\d+)\s+([0-9.]+)\s+([0-9.]+)\s*ms", line)
        if m:
            hops.append({
                "hop": int(m.group(1)),
                "ip": m.group(2),
                "rtt_ms": float(m.group(3)),
            })
        elif re.match(r"^(\d+)\s+\*", line):
            hop_num = int(line.split()[0])
            hops.append({"hop": hop_num, "ip": "*", "rtt_ms": None})

    return {
        "ok": len(hops) > 0,
        "target": target,
        "hops": hops,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    # Subcommands
    p_wifi = sub.add_parser("wifi-recon", help="Scan surrounding Wi-Fi networks")
    p_wifi.add_argument("--iface", default="wlan0")

    p_lan = sub.add_parser("lan-sweep", help="Discover live LAN neighbors")
    p_lan.add_argument("--iface", default="wlan0")

    p_port = sub.add_parser("port-scan", help="Scan open ports on target host")
    p_port.add_argument("target")
    p_port.add_argument("--ports", default="22,80,443,112,5050,8080,11434")

    p_dns = sub.add_parser("dns-audit", help="Audit DNS latency and resolution")
    p_dns.add_argument("--domain", default="google.com")
    p_dns.add_argument("--server", default=None)

    p_pcap = sub.add_parser("packet-sample", help="Sample packets on interface")
    p_pcap.add_argument("--iface", default="wlan0")
    p_pcap.add_argument("--count", type=int, default=10)

    p_trace = sub.add_parser("traceroute", help="Trace route to target IP")
    p_trace.add_argument("target", default="8.8.8.8", nargs="?")
    p_trace.add_argument("--max-hops", type=int, default=8)

    args = parser.parse_args()

    if args.cmd == "wifi-recon":
        res = wifi_recon(args.iface)
    elif args.cmd == "lan-sweep":
        res = lan_sweep(args.iface)
    elif args.cmd == "port-scan":
        res = port_scan(args.target, args.ports)
    elif args.cmd == "dns-audit":
        res = dns_audit(args.domain, args.server)
    elif args.cmd == "packet-sample":
        res = packet_sample(args.iface, args.count)
    elif args.cmd == "traceroute":
        res = route_trace(args.target, args.max_hops)
    else:
        res = {"ok": False, "error": "unknown command"}

    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
