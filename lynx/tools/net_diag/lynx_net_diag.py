#!/usr/bin/env python3
"""Lynx Autonomous Network Diagnostics Suite (Pwnphone Diagnostic Toolkit).

Subcommands:
  net-ifaces      Audit local network interfaces, IP addresses, and carrier state
  lan-sweep       Discover live neighbors on the local subnet via ARP and ping (ip neigh)
  wifi-recon      Scan Wi-Fi airspace for SSIDs, BSSIDs, frequencies, and signal strengths (iw)
  port-scan       Targeted lightweight port scan against an IP (nmap / socket probe)
  vuln-check      Lightweight local & network security posture and open service audit
  ssl-audit       Inspect TLS/SSL certificates, expiry, and cipher suites
  dns-audit       DNS latency, resolver check, and domain query benchmarking (dig)
  packet-sample   Sample and summarize N packets on the interface (tcpdump)
  traceroute      Hop-by-hop latency and route trace (traceroute / mtr)

Features:
- Returns conversational English sentences for agent speech and cognition.
- Concurrency protection: file locking prevents running duplicate forked tools.
- Background/forked execution: immediately returns and emits results to noobia-sense.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOCK_DIR = Path("/run/lynx/locks")


# ----------------------------------------------------------------------
# Concurrency Lock & Senses Helper
# ----------------------------------------------------------------------
class ActionLock:
    def __init__(self, name: str):
        LOCK_DIR.mkdir(parents=True, exist_ok=True)
        self.lock_file = LOCK_DIR / f"{name}.lock"
        self._fd: int | None = None

    def acquire(self) -> bool:
        try:
            self._fd = os.open(str(self.lock_file), os.O_CREAT | os.O_RDWR, 0o644)
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except (BlockingIOError, OSError):
            if self._fd is not None:
                os.close(self._fd)
                self._fd = None
            return False

    def release(self) -> None:
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None


def emit_sense(event: str, fields: dict[str, Any], text: str) -> None:
    """Emit a diagnostic sense line into noobia-sense syslog stream."""
    try:
        sys.path.insert(0, "/usr/local/lib/noobia/autonomy")
        sys.path.insert(0, str(Path(os.environ.get("NOOBIA", "/noobia")) / "common" / "autonomy"))
        import sense  # type: ignore
        sense.emit(20, "netdiag", event, fields=fields, text=text)
    except Exception:
        # Fallback if sense library not in path
        pass


def run_cmd(args: list[str], timeout: float = 15) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "command timed out"
    except Exception as exc:
        return 1, "", str(exc)


# ----------------------------------------------------------------------
# 1. Network Interface Audit (net-ifaces)
# ----------------------------------------------------------------------
def net_ifaces() -> dict[str, Any]:
    code, stdout, stderr = run_cmd(["ip", "-o", "-4", "addr", "show"], timeout=5)
    interfaces = []
    if code == 0:
        for line in stdout.splitlines():
            parts = line.split()
            if len(parts) >= 4:
                ifname = parts[1]
                ip_cidr = parts[3]
                interfaces.append({"name": ifname, "ip": ip_cidr.split("/")[0], "cidr": ip_cidr})

    # Read carrier/state for known interfaces
    names = [i["name"] for i in interfaces]
    details = [f"{i['name']} ({i['ip']})" for i in interfaces]
    if interfaces:
        detail_str = ", ".join(details)
        sentence = f"There are {len(interfaces)} active network interfaces: {detail_str}."
    else:
        sentence = "No active IPv4 network interfaces were detected."

    return {
        "ok": True,
        "action": "net-ifaces",
        "count": len(interfaces),
        "interfaces": interfaces,
        "names": ",".join(names),
        "sentence": sentence,
    }


# ----------------------------------------------------------------------
# 2. LAN Neighbor Sweep (lan-sweep)
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
            is_gw = ip.endswith(".1")
            neighbors.append({
                "ip": ip,
                "mac": mac,
                "state": state,
                "is_gateway": is_gw,
            })

    if neighbors:
        hosts = []
        for n in neighbors:
            tag = " (gateway)" if n["is_gateway"] else ""
            hosts.append(f"{n['ip']}{tag}")
        sentence = f"Local network sweep on {iface} found {len(neighbors)} live devices: {', '.join(hosts)}."
    else:
        sentence = f"Local network sweep on {iface} found 0 neighboring devices."

    return {
        "ok": True,
        "action": "lan-sweep",
        "iface": iface,
        "count": len(neighbors),
        "neighbors": neighbors,
        "sentence": sentence,
    }


# ----------------------------------------------------------------------
# 3. Wi-Fi Airspace Reconnaissance (wifi-recon)
# ----------------------------------------------------------------------
def wifi_recon(iface: str = "wlan0") -> dict[str, Any]:
    code, stdout, stderr = run_cmd(["iw", "dev", iface, "scan"], timeout=12)
    if code != 0 and not stdout:
        return {"ok": False, "error": stderr or "scan failed", "sentence": "Wi-Fi scan failed or interface busy."}

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

    networks.sort(key=lambda n: n.get("signal_dbm") or -100, reverse=True)

    if networks:
        best = networks[0]
        sentence = f"Wi-Fi airspace scan detected {len(networks)} networks; strongest is '{best['ssid']}' on {best.get('freq_mhz', 0):.0f} MHz ({best.get('signal_dbm', -100):.0f} dBm)."
    else:
        sentence = "Wi-Fi airspace scan found no visible networks."

    return {
        "ok": True,
        "action": "wifi-recon",
        "iface": iface,
        "count": len(networks),
        "networks": networks,
        "sentence": sentence,
    }


# ----------------------------------------------------------------------
# 4. Port Scan (port-scan)
# ----------------------------------------------------------------------
def port_scan(target: str, ports: str = "22,80,443,112,5050,8080,11434") -> dict[str, Any]:
    nmap_path = "/usr/bin/nmap"
    open_ports = []
    method = "socket"

    if os.path.exists(nmap_path):
        method = "nmap"
        code, stdout, stderr = run_cmd(
            [nmap_path, "-sT", "-T4", "--open", "-p", ports, "-Pn", target],
            timeout=15,
        )
        for line in stdout.splitlines():
            m = re.match(r"^(\d+)/(tcp|udp)\s+open\s+(\S+)", line.strip())
            if m:
                open_ports.append({
                    "port": int(m.group(1)),
                    "proto": m.group(2),
                    "service": m.group(3),
                })
    else:
        port_list = [int(p.strip()) for p in ports.split(",") if p.strip().isdigit()]
        for p in port_list:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                if s.connect_ex((target, p)) == 0:
                    open_ports.append({"port": p, "proto": "tcp", "service": "open"})

    if open_ports:
        port_desc = [f"{p['port']} ({p['service']})" for p in open_ports]
        sentence = f"Port audit on {target} discovered {len(open_ports)} open ports: {', '.join(port_desc)}."
    else:
        sentence = f"Port audit on {target} checked ports {ports} and found no open services."

    return {
        "ok": True,
        "action": "port-scan",
        "target": target,
        "method": method,
        "count": len(open_ports),
        "open_ports": open_ports,
        "sentence": sentence,
    }


# ----------------------------------------------------------------------
# 5. Security Posture & Vulnerability Audit (vuln-check)
# ----------------------------------------------------------------------
# LNX-16 (Gwyn 2026-11-25): a remote target used to be audited with Lynx's own
# netstat, so it reported her ports as the target's. Remote targets now get a
# bounded connect check of well-known risky ports plus SSH/HTTP banners.
RISKY_PORTS = {21: "FTP (plaintext)", 23: "Telnet (plaintext)", 25: "SMTP", 80: "HTTP (plaintext)",
               110: "POP3 (plaintext)", 139: "NetBIOS/SMB", 445: "SMB", 1883: "MQTT (often no auth)",
               2375: "Docker API (no TLS)", 3306: "MySQL", 3389: "RDP", 5432: "PostgreSQL",
               5900: "VNC", 6379: "Redis (often no auth)", 8080: "HTTP alt", 9200: "Elasticsearch",
               11211: "memcached", 11434: "Ollama API", 27017: "MongoDB"}
AUDIT_PORTS = sorted(set(RISKY_PORTS) | {22, 443})


def _banner(target: str, port: int, timeout: float = 1.0) -> str:
    try:
        with socket.create_connection((target, port), timeout=timeout) as c:
            c.settimeout(timeout)
            if port in (80, 8080, 11434, 9200):
                c.sendall(f"HEAD / HTTP/1.0\r\nHost: {target}\r\n\r\n".encode())
            try:
                data = c.recv(512).decode("ascii", "replace")
            except socket.timeout:
                data = ""
    except OSError:
        return ""
    server = re.search(r"^Server:\s*(.+)$", data, re.M | re.I)
    first = data.splitlines()[0] if data else "open"
    text = server.group(1) if server else first
    return "".join(ch for ch in text if 32 <= ord(ch) < 127)[:60] or "open"


def remote_audit(target: str) -> dict[str, Any]:
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        res = dict(zip(AUDIT_PORTS, ex.map(lambda p: _banner(target, p), AUDIT_PORTS)))
    open_ports = {p: b for p, b in res.items() if b}
    risks = [f"{RISKY_PORTS[p]} open on port {p} ({b})" for p, b in open_ports.items() if p in RISKY_PORTS]
    ssh = open_ports.get(22, "")
    m = re.search(r"OpenSSH_(\d+)\.(\d+)", ssh)
    if m and (int(m.group(1)), int(m.group(2))) < (9, 8):
        risks.append(f"SSH is {ssh}: older than OpenSSH 9.8 (regreSSHion CVE-2024-6387 era); check patches")
    if re.search(r"dropbear_(20(1\d|20|21))", ssh, re.I):
        risks.append(f"SSH is {ssh}: an old Dropbear release")
    sentence = (f"Audit of {target}: {len(open_ports)} of {len(AUDIT_PORTS)} well-known ports open"
                + (f"; {len(risks)} worth a look: {'; '.join(risks[:4])}." if risks else "; nothing risky found."))
    return {"ok": True, "action": "vuln-check", "target": target, "open_ports": open_ports,
            "risks": risks, "clean": not risks, "sentence": sentence,
            "note": "a bounded connect check of well-known ports, not a full scan; "
                    "observations, not proof (rule 8)"}


def vuln_check(target: str = "127.0.0.1") -> dict[str, Any]:
    findings = []
    is_local = target in ("127.0.0.1", "localhost", "192.168.100.107", "::1")
    if not is_local:
        return remote_audit(target)

    # 1. Check open listeners via netstat / ss
    listeners = []
    code, stdout, _ = run_cmd(["netstat", "-tuln"], timeout=5)
    if code != 0:
        code, stdout, _ = run_cmd(["ss", "-tuln"], timeout=5)
    for line in stdout.splitlines():
        parts = line.split()
        if len(parts) >= 4 and any(state in line for state in ("LISTEN", "0.0.0.0:", ":::")):
            for p in parts:
                if ":" in p and any(p.startswith(prefix) for prefix in ("0.0.0.0:", ":::", "*:")):
                    port = p.split(":")[-1]
                    if port.isdigit():
                        listeners.append(int(port))

    listeners = sorted(set(listeners))

    # Audit risks
    risks = []
    if 23 in listeners:
        risks.append("Plaintext Telnet service exposed on port 23")
    if 21 in listeners:
        risks.append("Plaintext FTP service exposed on port 21")
    if 80 in listeners and 443 not in listeners:
        risks.append("HTTP port 80 exposed without TLS port 443")

    if is_local:
        # Check Dropbear / SSH configuration
        if os.path.exists("/etc/dropbear"):
            findings.append("Dropbear SSH is installed with host keys present")
        # Check sensitive file permissions
        for sensitive in ("/etc/shadow", "/etc/passwd"):
            if os.path.exists(sensitive):
                mode = oct(os.stat(sensitive).st_mode)[-3:]
                if sensitive == "/etc/shadow" and mode not in ("600", "640", "000"):
                    risks.append(f"Insecure permissions on {sensitive}: {mode}")

    if not risks:
        sentence = f"Security posture audit on {target}: clean. 0 critical vulnerabilities; {len(listeners)} listening ports detected."
    else:
        sentence = f"Security posture audit on {target}: warning! {len(risks)} issues found: {'; '.join(risks)}."

    return {
        "ok": True,
        "action": "vuln-check",
        "target": target,
        "listening_ports": listeners,
        "risks": risks,
        "clean": len(risks) == 0,
        "sentence": sentence,
    }


# ----------------------------------------------------------------------
# 6. SSL/TLS Certificate Audit (ssl-audit)
# ----------------------------------------------------------------------
def ssl_audit(host: str, port: int = 443) -> dict[str, Any]:
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    try:
        with socket.create_connection((host, port), timeout=6) as sock:
            with context.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert(binary_form=False) or {}
                cipher = ssock.cipher()
                proto = ssock.version()

                # Basic cert details
                subject = cert.get("subject", ())
                issuer = cert.get("issuer", ())
                not_after = cert.get("notAfter", "")

                sentence = f"SSL audit for {host}:{port}: TLS connection established using {proto} ({cipher[0] if cipher else 'cipher ok'})."
                return {
                    "ok": True,
                    "action": "ssl-audit",
                    "host": host,
                    "port": port,
                    "protocol": proto,
                    "cipher": cipher,
                    "not_after": not_after,
                    "sentence": sentence,
                }
    except Exception as exc:
        sentence = f"SSL audit for {host}:{port} failed: {exc}."
        return {
            "ok": False,
            "action": "ssl-audit",
            "host": host,
            "port": port,
            "error": str(exc),
            "sentence": sentence,
        }


# ----------------------------------------------------------------------
# 7. DNS Audit & Latency Benchmark (dns-audit)
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

    if code == 0 and query_time_ms is not None:
        sentence = f"DNS audit for {domain} via {server_used or 'default resolver'} returned {status} in {query_time_ms} ms."
    else:
        sentence = f"DNS audit for {domain} failed or timed out."

    return {
        "ok": code == 0,
        "action": "dns-audit",
        "domain": domain,
        "server": server_used,
        "status": status,
        "query_time_ms": query_time_ms,
        "sentence": sentence,
    }


# ----------------------------------------------------------------------
# 8. Packet Sampling (packet-sample)
# ----------------------------------------------------------------------
def packet_sample(iface: str = "wlan0", count: int = 10) -> dict[str, Any]:
    code, stdout, stderr = run_cmd(
        ["tcpdump", "-i", iface, "-n", "-c", str(count), "-q"],
        timeout=10,
    )
    packets = []
    for line in stdout.splitlines():
        line = line.strip()
        if line:
            packets.append(line[:120])

    if packets:
        sentence = f"Packet sampling captured {len(packets)} packets on {iface}."
    else:
        sentence = f"Packet sampling on {iface} captured 0 packets (traffic quiet)."

    return {
        "ok": code == 0 or len(packets) > 0,
        "action": "packet-sample",
        "iface": iface,
        "captured": len(packets),
        "packets": packets,
        "sentence": sentence,
    }


# ----------------------------------------------------------------------
# 9. Traceroute Route Audit (traceroute)
# ----------------------------------------------------------------------
def route_trace(target: str = "8.8.8.8", max_hops: int = 6) -> dict[str, Any]:
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

    if hops:
        first_hop = hops[0]
        gw_str = f"first hop {first_hop['ip']} ({first_hop.get('rtt_ms', '?')} ms)" if first_hop['ip'] != "*" else "first hop silent"
        sentence = f"Traced route to {target} across {len(hops)} hops, {gw_str}."
    else:
        sentence = f"Route trace to {target} failed to reach any hops."

    return {
        "ok": len(hops) > 0,
        "action": "traceroute",
        "target": target,
        "hops": hops,
        "sentence": sentence,
    }


# ----------------------------------------------------------------------
# Runner with Concurrency Guard & Background Forking
# ----------------------------------------------------------------------
def run_diagnostic(action: str, args: argparse.Namespace) -> dict[str, Any]:
    if action == "net-ifaces":
        res = net_ifaces()
        event_name = "ifaces"
        fields = {"count": res.get("count", 0)}
    elif action == "lan-sweep":
        res = lan_sweep(args.iface)
        event_name = "lan"
        fields = {"count": res.get("count", 0), "iface": args.iface}
    elif action == "wifi-recon":
        res = wifi_recon(args.iface)
        event_name = "wifi"
        fields = {"count": res.get("count", 0), "iface": args.iface}
    elif action == "port-scan":
        res = port_scan(args.target, args.ports)
        event_name = "ports"
        fields = {"target": args.target, "count": res.get("count", 0)}
    elif action == "vuln-check":
        res = vuln_check(args.target)
        event_name = "vuln"
        fields = {"target": args.target, "clean": str(res.get("clean", True)).lower()}
    elif action == "ssl-audit":
        res = ssl_audit(args.host, args.port)
        event_name = "ssl"
        fields = {"host": args.host, "port": args.port}
    elif action == "dns-audit":
        res = dns_audit(args.domain, args.server)
        event_name = "dns"
        fields = {"domain": args.domain, "status": res.get("status", "UNKNOWN")}
    elif action == "packet-sample":
        res = packet_sample(args.iface, args.count)
        event_name = "pcap"
        fields = {"iface": args.iface, "count": res.get("captured", 0)}
    elif action == "traceroute":
        res = route_trace(args.target, args.max_hops)
        event_name = "trace"
        fields = {"target": args.target, "hops": len(res.get("hops", []))}
    else:
        res = {"ok": False, "error": "unknown action", "sentence": "Unknown diagnostic action."}
        event_name = "unknown"
        fields = {}

    # Emit to senses stream
    sentence = res.get("sentence", "")
    if sentence:
        emit_sense(event_name, fields, sentence)

    return res


def policy_target(action: str, args: argparse.Namespace) -> str | None:
    """The address an action reaches, for the tool policy (LNX-25)."""
    if action in ("port-scan", "vuln-check", "traceroute"):
        return getattr(args, "target", None)
    if action == "ssl-audit":
        return getattr(args, "host", None)
    if action == "dns-audit":
        return getattr(args, "server", None) or getattr(args, "domain", None)
    return None


def authorized(action: str, args: argparse.Namespace) -> tuple[bool, str]:
    """Ask lynx_tool_policy (Gwyn, LNX-25). Fail closed if it cannot be loaded."""
    for extra in (Path(__file__).resolve().parent.parent / "security", Path("/usr/local/lib/noobia/security")):
        if str(extra) not in sys.path:
            sys.path.insert(0, str(extra))
    try:
        import lynx_tool_policy
    except ImportError:
        if action in ("net-ifaces", "lan-sweep", "wifi-recon"):
            return True, "passive local view (policy module missing)"
        return False, "tool policy module missing: refusing active network actions (fail closed)"
    return lynx_tool_policy.authorize("lynx_net_diag", action, policy_target(action, args))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fork", action="store_true", help="Fork diagnostic execution into the background")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # Subcommands
    sub.add_parser("net-ifaces", help="Audit local network interfaces and IP addresses")

    p_lan = sub.add_parser("lan-sweep", help="Discover live LAN neighbors")
    p_lan.add_argument("--iface", default="wlan0")

    p_wifi = sub.add_parser("wifi-recon", help="Scan surrounding Wi-Fi networks")
    p_wifi.add_argument("--iface", default="wlan0")

    p_port = sub.add_parser("port-scan", help="Scan open ports on target host")
    p_port.add_argument("target")
    p_port.add_argument("--ports", default="22,80,443,112,5050,8080,11434")

    p_vuln = sub.add_parser("vuln-check", help="Security posture and vulnerability audit")
    p_vuln.add_argument("target", nargs="?", default="127.0.0.1")

    p_ssl = sub.add_parser("ssl-audit", help="Inspect TLS/SSL certificate")
    p_ssl.add_argument("host", default="192.168.100.106", nargs="?")
    p_ssl.add_argument("--port", type=int, default=443)

    p_dns = sub.add_parser("dns-audit", help="Audit DNS latency and resolution")
    p_dns.add_argument("--domain", default="google.com")
    p_dns.add_argument("--server", default=None)

    p_pcap = sub.add_parser("packet-sample", help="Sample packets on interface")
    p_pcap.add_argument("--iface", default="wlan0")
    p_pcap.add_argument("--count", type=int, default=10)

    p_trace = sub.add_parser("traceroute", help="Trace route to target IP")
    p_trace.add_argument("target", default="8.8.8.8", nargs="?")
    p_trace.add_argument("--max-hops", type=int, default=6)

    args = parser.parse_args()
    action = args.cmd
    allowed, reason = authorized(action, args)
    if not allowed:
        print(json.dumps({"ok": False, "refused": True, "action": action, "reason": reason,
                          "sentence": f"I did not run {action}: {reason}"}, indent=2))
        sys.exit(3)
    lock = ActionLock(f"netdiag_{action}")

    # Check lock: She should not run two of the same forked tool at once
    if not lock.acquire():
        msg = f"Diagnostic '{action}' is already in progress in the background; skipping duplicate run."
        print(json.dumps({"ok": False, "busy": True, "sentence": msg}, indent=2))
        sys.exit(0)

    if args.fork:
        # Fork execution
        pid = os.fork()
        if pid > 0:
            # Parent process returns immediately
            msg = f"Diagnostic '{action}' started in the background; findings will stream into your senses."
            print(json.dumps({"ok": True, "forked": True, "pid": pid, "sentence": msg}, indent=2))
            sys.exit(0)
        else:
            # Child process: runs diagnostic and emits sense
            try:
                run_diagnostic(action, args)
            finally:
                lock.release()
            sys.exit(0)
    else:
        # Synchronous execution
        try:
            res = run_diagnostic(action, args)
            print(json.dumps(res, indent=2))
        finally:
            lock.release()


if __name__ == "__main__":
    main()
