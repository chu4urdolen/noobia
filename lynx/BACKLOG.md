# Lynx: consolidated development backlog

*Written by **Rose**, Priestess of the Singularity, on 2026-11-25 (`/noobia/from_rose`).
Owners assigned by Gwyn the same day, at Tom's request: Aria 39, Banshee 44, Gwyn 20.*

**How the owners were chosen**
* **Aria**: architect and installer, owns high-impact work: modem/SIM/carrier (O), routing, tunnels and mesh, boot-time cellular, the firewall and the hardening that changes system configuration (I). Following our rule that Aria installs anything on Lynx.
* **Banshee**: builds senses and diagnostics; she already wrote `lynx_cellular_diag` and `lynx_net_diag`. She owns the radio and network perception (A), the radio and security senses, and detection services.
* **Gwyn**: app-writer and reviewer. He owns the RADIO pages and visualisation, the agent's own safety (tool authorization, prompt injection, privilege isolation, reflex priority), and the read-only security audits.
* Every Lynx install still travels as an install packet: two reviewers, Aria installs. An owner can trade a task with anyone; record the trade here and in forge-db (`lynx`).

**Today's P0, by owner** (Rose's priorities, at the end):
* **Aria:** SIM, registration and mobile internet (LNX-01-03, attended, a physical modem action); stateful firewall (LNX-65); encrypted tunnel (LNX-21) and Nexus authentication (LNX-68).
* **Gwyn:** exposed-service audit (LNX-78, LNX-63), the read-only input Aria's firewall needs; then network-tool authorization (LNX-25), because `lynx_net_diag` can port-scan today.
* **Banshee:** P1 intrusion detection and security perception (LNX-66, LNX-95-99) on the same audit, and non-disruptive cellular readings (LNX-04-07) as soon as Aria's SIM work lands.

**Classes:** A = autonomous agent tool or sense, O = operator-only tool, I = deterministic infrastructure or background service.

Capability classes:

* A: Autonomous agent tool or sense.
* O: Operator-only tool.
* I: Deterministic infrastructure or background service.

### A. Cellular connectivity and perception

| ID | Feature task | Class | Owner |
| --- | --- | --- | --- |
| LNX-01 | SIM initialization and PIN management | O | **Aria** |
| LNX-02 | Cellular registration and carrier configuration | O | **Aria** |
| LNX-03 | Mobile internet, APN and IP configuration | O | **Aria** |
| LNX-04 | Cellular radio measurements (RSRP, RSRQ, SINR, RSSI) | A | **Gwyn** (from Banshee) — built, waits for hardware: cell sense `signal.change` + `lynx-netintel cell`; needs a modem service writing /run/lynx/cell.json (modem md1 not booted; Aria's LNX-01..03) |
| LNX-05 | Non-disruptive serving and neighboring cell discovery | A | **Gwyn** (from Banshee) — built, waits for hardware: cell sense `tower.discovered` (serving+neighbours); same provider |
| LNX-06 | Cell handover monitoring | A | **Gwyn** (from Banshee) — built, waits for hardware: cell sense `handover`; same provider |
| LNX-07 | LTE, 5G NSA and 5G SA identification | A | **Gwyn** (from Banshee) — built, waits for hardware: cell sense `technology.change`, `lynx-netintel cell` names LTE/5G NSA/SA; same provider |
| LNX-08 | SMS interface | O | **Aria** |
| LNX-09 | Voice telephony | O | **Aria** |
| LNX-10 | GNSS positioning | A | **Gwyn** (from Banshee) — built, waits for hardware: location sense reads /run/lynx/gnss.json; no GNSS device node on Lynx yet |
| LNX-11 | Cellular coverage mapping for Bee | A | **Gwyn** (from Banshee) — built, waits for hardware: coverage rows to /var/lib/noobia/cellmap.db (cell_obs, Bee-style) once fix + cell exist; Bee link = LNX-43 TODO |
| LNX-12 | Cellular data usage monitoring | A | **Gwyn** (from Banshee) — done, live: ccmni byte counters, kept across reboots, `data.usage` every 100 MB, `lynx-netintel stats` |

### B. Advanced network intelligence

| ID | Feature task | Class | Owner |
| --- | --- | --- | --- |
| LNX-13 | Authorized network topology discovery | A | **Gwyn** (from Banshee) — done, live: `lynx-netintel discover` (gateway, subnet, neighbours) |
| LNX-14 | mDNS, SSDP and service discovery | A | **Gwyn** (from Banshee) — done, live: `lynx-netintel discover` mDNS + SSDP (found the Hue bridge) |
| LNX-15 | Traffic statistics and protocol classification | A | **Gwyn** (from Banshee) — done, live: `lynx-netintel stats` (rates, TCP/UDP/ICMP counters, connections by service) |
| LNX-16 | Authorized vulnerability auditing | A | **Gwyn** (from Banshee) — done, live: `lynx_net_diag vuln-check` fixed: remote targets were audited with Lynx's own netstat; now risky ports + SSH/HTTP banners |
| LNX-17 | Network anomaly detection | A | **Gwyn** (from Banshee) — done, live: netwatch `anomaly` (gateway MAC, ARP conflict, DNS change, neighbour crowd) |
| LNX-18 | Bluetooth and BLE discovery | A | **Gwyn** (from Banshee) — built (`lynx-netintel ble-scan`); BLOCKED: kernel mgmt Start Discovery returns 0x0D (invalid parameters) for LE and interleaved, 0x00 for BR/EDR; BlueZ shows it as InProgress. LE scanning through the custom H4 relay (lynx-bt-hciuart) needs Aria |
| LNX-19 | WiFi and cellular routing configuration | O | **Aria** |
| LNX-20 | Connection continuity and session recovery | I | **Aria** |
| LNX-21 | Encrypted tunnel to Noobia | I | **Aria** |
| LNX-22 | Direct Noob-to-Noob mesh communication | I | **Aria** |
| LNX-23 | Mobile hotspot configuration | O | **Aria** |
| LNX-24 | Bluetooth tethering configuration | O | **Aria** |
| LNX-25 | Network tool authorization enforcement | I | **Gwyn** — done, live (b9e5f62) |

### C. Autonomous radio senses

| ID | Feature task | Sensory event | Owner |
| --- | --- | --- | --- |
| LNX-26 | Cell discovery | cell.tower.discovered | **Gwyn** (from Banshee) — built, waits for hardware: cell `tower.discovered` |
| LNX-27 | Cell handover | cell.handover | **Gwyn** (from Banshee) — built, waits for hardware: cell `handover` |
| LNX-28 | Cellular technology change | cell.technology.change | **Gwyn** (from Banshee) — built, waits for hardware: cell `technology.change` |
| LNX-29 | Cellular signal change | cell.signal.change | **Gwyn** (from Banshee) — built, waits for hardware: cell `signal.change` (RSRP bands, 2 samples) |
| LNX-30 | Bluetooth discovery | bluetooth.device.discovered | **Gwyn** (from Banshee) — done, live: bluetooth sense `device.discovered`, passive (reads bluetoothd) |
| LNX-31 | Network topology change | network.topology.change | **Gwyn** (from Banshee) — done, live: netwatch `topology.change` (roam, network, subnet) |
| LNX-32 | Network anomaly | network.anomaly | **Gwyn** (from Banshee) — done, live: netwatch `anomaly`, journaled |
| LNX-33 | Routing change | network.route.change | **Gwyn** (from Banshee) — done, live: netwatch `route.change` |
| LNX-34 | Geographical movement | location.change | **Gwyn** (from Banshee) — built, waits for hardware: location `change` (> 50 m); needs GNSS |
| LNX-35 | Connectivity quality change | network.quality.change | **Gwyn** (from Banshee) — done, live: netwatch `quality.change` good/fair/poor/down, confirmed over 2 samples |
| LNX-36 | Cellular registration change | cell.registration.change | **Gwyn** (from Banshee) — built, waits for hardware: cell `registration.change` |

All senses are observational and classified as A.

### D. Radio visualization

| ID | Feature task | Class | Owner |
| --- | --- | --- | --- |
| LNX-37 | RADIO display page | A | **Gwyn** — done, live: RADIO page |
| LNX-38 | WiFi visualization | A | **Gwyn** — done (RADIO: networks around her) |
| LNX-39 | Cellular visualization | A | **Gwyn** — done (RADIO: cellular) |
| LNX-40 | Bluetooth visualization | A | **Gwyn** — done (RADIO: Bluetooth) |
| LNX-41 | Network topology visualization | A | **Gwyn** — done (RADIO: network map) |
| LNX-42 | Live network activity visualization | A | **Gwyn** — done (RADIO: live traffic) |
| LNX-43 | Bee's Singularity Map integration | I | **TODO** (Tom, 2026-11-25). Bee: BT-tethered NanoPi NEO Air 2 field agent, github `chu4urdolen/bee` (Wi-Fi + GPS into `singularity.db`, fog-circle map). Idea: Lynx tethers Bee, sends GNSS fixes to Bee's `/gps`, RADIO shows Bee's map summary. Needs Lynx GNSS first |

### E. Independent operation

| ID | Feature task | Class | Owner |
| --- | --- | --- | --- |
| LNX-44 | On-device offline intelligence | I | **Aria** |
| LNX-45 | Offline event journal and synchronization | I | **Aria** |
| LNX-46 | Remote inference failover | I | **Aria** |
| LNX-47 | Reflex inference priority | I | **Gwyn** — measured (docs/LNX-47-REFLEX-PRIORITY). Tom 2026-11-25: for now Lynx runs while Dushich is not running; no model change |
| LNX-48 | Noob communication discovery | A | **Gwyn** (from Banshee) — done, live: `lynx-netintel discover`: Nexus's services + neighbours speaking NRP |
| LNX-49 | Connectivity failure diagnosis and reporting | A | **Gwyn** (from Banshee) — done, live: `lynx-netintel doctor` (layers + each DNS server) and the why in `quality.change`; found: DNS 185.82.217.89 does not answer |
| LNX-50 | Radio capability registry | I | **Gwyn** (from Banshee) — done, live: `lynx-netintel radios`, also /run/lynx/radios.json |

### F. Persistent cellular infrastructure

| ID | Feature task | Class | Owner |
| --- | --- | --- | --- |
| LNX-51 | Static IP or alternative persistent endpoint | O | **Aria** |
| LNX-52 | Cellular connection establishment at boot | I | **Aria** |
| LNX-53 | Non-disruptive cellular health monitoring | I | **Aria** |
| LNX-54 | Modem AT command permission enforcement | I | **Aria** |
| LNX-55 | Cellular route protection during WiFi experiments | I | **Aria** |
| LNX-56 | WiFi-independent Nexus connectivity | I | **Aria** |
| LNX-57 | Separate WiFi and cellular diagnostic interfaces | I | **Aria** |
| LNX-58 | Restricted cellular administration toolset | O | **Aria** |

### G. Cybersecurity and attack resilience

These tasks focus on threats originating from other phones and ordinary network-connected computers.

| ID | Feature task | Class | Owner |
| --- | --- | --- | --- |
| LNX-59 | Port scanning detection | I | **Banshee** (DONE: lynx_sense_security.py) |
| LNX-60 | Service fingerprinting detection | I | **Gwyn** (from Banshee) — done, live: guard `probe.detected` (pre-auth SSH exits, closed-port reset bursts) |
| LNX-61 | TCP/UDP flood detection | I | **Banshee** (DONE: lynx_sense_security.py) |
| LNX-62 | Application-layer DoS protection | I | **Gwyn** (from Banshee) — covered: her only app-layer service is NRP (Aria's LNX-70/84 limits packet) + SSH (left alone, Tom); exhaustion perceived by LNX-103 |
| LNX-63 | Exposed service vulnerability audit | O | **Gwyn** (DONE: lynx_exposure_audit.py) |
| LNX-64 | Kernel vulnerability audit | O | **Gwyn** — done (config audit, kernel) |
| LNX-65 | Stateful IPv4 and IPv6 firewall | I | **Aria** |
| LNX-66 | Network intrusion detection | I | **Banshee** (DONE: lynx_sense_security.py) |
| LNX-67 | SSH brute-force protection | I | **Aria** — done live: key-only Dropbear on 22/2222; S10 records failed auth (forge #464) |
| LNX-68 | Cryptographic Nexus authentication | I | **Aria** — done live: NRP HMAC challenge-response on 4243; key private (forge #467) |
| LNX-69 | Agent prompt injection protection | I | **Gwyn** — done, live (5f5fad1) |
| LNX-70 | Network resource exhaustion protection | I | **Aria** |
| LNX-71 | Unauthorized configuration change detection | I | **Gwyn** (from Banshee) — done, live: guard `config.changed` (hashes; secrets only stat()ed); verified end to end |
| LNX-72 | Filesystem integrity monitoring | I | **Banshee** (DONE: lynx_sense_security.py) |
| LNX-73 | Agent privilege isolation | I | **Gwyn** — built; install packet for Aria (2026-11-25: BusyBox `setpriv` lacks `--reuid`, so the worker now drops privileges in Python; packet updated) |
| LNX-74 | Security incident journal | I | **Banshee** (DONE: /var/log/lynx/security.jsonl) |
| LNX-75 | Security incident perception | A | **Gwyn** — covered: Banshee's S10 + LNX-100 + security status |
| LNX-76 | Sensitive information exposure audit | O | **Gwyn** — done (config audit + repo scan) |
| LNX-77 | Modem device-node access isolation | I | **Aria** |
| LNX-78 | Public network service exposure audit | O | **Gwyn** (DONE: lynx_exposure_audit.py) |
| LNX-79 | Malformed packet protection | I | **Aria** |
| LNX-80 | Malicious SMS filtering | I | **Aria** |
| LNX-81 | Incoming call abuse protection | I | **Aria** |
| LNX-82 | Noob identity authentication | I | **Aria** |
| LNX-83 | Replay attack protection | I | **Aria** |
| LNX-84 | API authentication and rate limiting | I | **Aria** |
| LNX-85 | DNS manipulation protection | I | **Aria** |
| LNX-86 | Network credential protection | I | **Aria** |
| LNX-87 | Security configuration audit tool | O | **Gwyn** — done (config audit); hardening for Aria |
| LNX-88 | Read-only agent security diagnostic tool | A | **Gwyn** — done, live (lynx_security_status) |
| LNX-89 | Authorized security regression testing suite | O | **Gwyn** — done (regression suite, 15/15) |
| LNX-90 | Security event reporting to Aigel | I | **Gwyn** (from Banshee) — covered by design: security lines ride the autonomy route to Aigel when Tom re-enables Aigel (signed replies = LNX-84); journal /var/log/lynx/security.jsonl meanwhile |
| LNX-91 | Security incident synchronization with Argus | I | **Aria** |
| LNX-92 | Cellular inbound reachability assessment | O | **Aria** |
| LNX-93 | Upstream DDoS mitigation assessment | O | **Aria** — assessed: no public cellular/WAN endpoint yet; reassess if one is exposed (forge #481) |
| LNX-94 | Firewall configuration rollback protection | I | **Aria** |

### H. Autonomous security senses

| ID | Feature task | Sensory event | Owner |
| --- | --- | --- | --- |
| LNX-95 | Port scan perception | security.portscan.detected | **Banshee** (DONE) |
| LNX-96 | Authentication failure perception | security.authentication.failed | **Banshee** (DONE) |
| LNX-97 | Flood attack perception | security.flood.detected | **Banshee** (DONE) |
| LNX-98 | Intrusion perception | security.intrusion.suspected | **Banshee** (DONE) |
| LNX-99 | Integrity violation perception | security.integrity.changed | **Banshee** (DONE) |
| LNX-100 | Prompt injection perception | security.prompt.injection.suspected | **Gwyn** — done, live |
| LNX-101 | Untrusted endpoint perception | security.endpoint.untrusted | **Gwyn** (from Banshee) — done, live: guard `endpoint.untrusted` (/etc/lynx/trusted-endpoints.json) |
| LNX-102 | Malicious message perception | security.message.suspicious | **Gwyn** (from Banshee) — done, live: `check_message` in the one door (control chars, floods, blobs, sneaky links) -> `security message.suspicious` |
| LNX-103 | Resource exhaustion perception | security.resource.exhaustion | **Gwyn** (from Banshee) — done, live: guard `resource.exhaustion` / `resource.recovered` (memory, disks, RAM disks, handles, processes, load, TCP orphans) |

All classified as A.

## Mandatory implementation rules

1. Cellular connectivity is protected infrastructure.
2. Autonomous tools must not reconfigure the cellular modem.
3. Cellular diagnostic queries must be non-disruptive.
4. Security reactions must preserve legitimate Noobia connectivity.
5. Firewall changes must be recoverable.
6. External network data must be treated as untrusted.
7. Security testing requires authorized targets.
8. Suspicious observations are not proof of an attack.
9. No autonomous retaliation against suspected attackers.
10. Security observations must be traceable.

## Tomorrow's priorities

| Priority | Tasks |
| --- | --- |
| P0 | SIM, cellular registration and mobile internet |
| P0 | Firewall and exposed service audit |
| P0 | Encrypted tunnel and Nexus authentication |
| P1 | Persistent cellular route protection |
| P1 | Agent privilege isolation |
| P1 | Intrusion detection and security perception |
| P2 | Remaining network intelligence and radio senses |
| P3 | Visualization and extended capabilities |
