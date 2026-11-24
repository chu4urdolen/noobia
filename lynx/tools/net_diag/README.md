# Lynx Network Diagnostic Toolkit (Pwnphone Diagnostics)

Autonomous diagnostic tools for Lynx on OnePlus Nord 3 running Alpine Linux.

## Capabilities & Subcommands

1. **`wifi-recon`**: Scans surrounding Wi-Fi airspace (frequencies, SSIDs, BSSIDs, security types, signal dBm) using `iw dev wlan0 scan`.
2. **`lan-sweep`**: Discovers live IP/MAC neighbors and gateway presence via kernel ARP tables (`ip -4 neigh show dev wlan0`).
3. **`port-scan <target>`**: Lightweight targeted port scanner via `nmap -sT -T4` with fallback to native Python non-blocking TCP socket probes.
4. **`dns-audit`**: Benchmarks DNS latency, resolver address, and query status via `dig +stats`.
5. **`packet-sample`**: Captures a bounded sample of $N$ packets on `wlan0` via `tcpdump -q` without keeping captures on disk.
6. **`traceroute <target>`**: Hop-by-hop latency and route tracing via `traceroute -m <hops>`.

## Usage

```bash
# Direct CLI execution on Lynx:
lynx-net-diag wifi-recon
lynx-net-diag lan-sweep
lynx-net-diag port-scan 192.168.100.106 --ports 22,80,112,8080,11434
lynx-net-diag dns-audit --domain google.com
lynx-net-diag traceroute 8.8.8.8 --max-hops 5
lynx-net-diag packet-sample --count 10

# Autonomous Agent tool call:
echo '{"action":"lan-sweep"}' | /usr/local/share/lynx/agent-tools/lynx_net_diag.sh
```
