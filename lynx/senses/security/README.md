# Lynx Security Sense (S10)

Autonomous intrusion detection and attack resilience sense for Lynx.
Implements Rose's Backlog (2026-11-25) security tasks:
- **LNX-66 / LNX-98**: Intrusion detection & unexpected listener discovery (`security.intrusion.suspected`)
- **LNX-59 / LNX-95**: Port scan perception (`security.portscan.detected`)
- **LNX-67 / LNX-96**: Authentication failure perception (`security.authentication.failed`)
- **LNX-61 / LNX-97**: TCP/UDP flood attack perception (`security.flood.detected`)
- **LNX-72 / LNX-99**: System file integrity monitoring (`security.integrity.changed`)
- **LNX-74**: Security incident journal (`/var/log/lynx/security.jsonl`)

## Rose's Implementation Rules

1. **Rule 8 (Observations, not proof):** Suspicious observations are logged as observations, not proof of an attack.
2. **Rule 9 (No retaliation):** No autonomous retaliation against suspected attackers.
3. **Rule 10 (Traceable):** All security observations are traceable, durable, and logged to the incident journal.
4. **Rule 4 (Preserve connectivity):** Detection runs purely read-only and never disrupts legitimate Noobia connections.

## Monitored Indicators

1. **Unexpected Network Listeners:**
   - Reads `/proc/net/tcp` and `/proc/net/udp`.
   - Baseline expected listeners:
     - TCP 22: Early-boot rescue SSH (dropbear)
     - TCP 2222: Alpine SSH (dropbear)
     - TCP 4243: NRP daemon to Nexus (lynx-noobd)
   - Any other listening socket triggers `security.intrusion.suspected`.
2. **Port Scan Probes:**
   - Scans `/proc/net/tcp` for foreign IPs targeting multiple ports in `SYN_RECV` state (`03`).
   - Emits `security.portscan.detected` when multiple ports are probed simultaneously.
3. **Authentication Failures:**
   - Tracks offset into dropbear logs (`/run/lynx/alpine-dropbear-2222.log` and `/run/lynx/dropbear.log`).
   - Parses password attempts, invalid users, and key failures.
   - Emits `security.authentication.failed` with failed count, user, and source IP.
4. **Traffic Surges & Floods:**
   - Reads `/proc/net/dev` rx_packets and rx_bytes on `wlan0`.
   - Emits `security.flood.detected` if packet arrival rate crosses 1500 pps.
5. **System Configuration Integrity:**
   - Tracks SHA-256 baseline hashes of `/etc/passwd`, `/etc/shadow`, `/root/.ssh/authorized_keys`, `/etc/dropbear/authorized_keys`, `/etc/inittab`.
   - Emits `security.integrity.changed` if any file is modified.
6. **Incident Journal (`LNX-74`):**
   - All events append structured JSON lines to `/var/log/lynx/security.jsonl`.
