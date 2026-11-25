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
| LNX-04 | Cellular radio measurements (RSRP, RSRQ, SINR, RSSI) | A | **Banshee** |
| LNX-05 | Non-disruptive serving and neighboring cell discovery | A | **Banshee** |
| LNX-06 | Cell handover monitoring | A | **Banshee** |
| LNX-07 | LTE, 5G NSA and 5G SA identification | A | **Banshee** |
| LNX-08 | SMS interface | O | **Aria** |
| LNX-09 | Voice telephony | O | **Aria** |
| LNX-10 | GNSS positioning | A | **Banshee** |
| LNX-11 | Cellular coverage mapping for Bee | A | **Banshee** |
| LNX-12 | Cellular data usage monitoring | A | **Banshee** |

### B. Advanced network intelligence

| ID | Feature task | Class | Owner |
| --- | --- | --- | --- |
| LNX-13 | Authorized network topology discovery | A | **Banshee** |
| LNX-14 | mDNS, SSDP and service discovery | A | **Banshee** |
| LNX-15 | Traffic statistics and protocol classification | A | **Banshee** |
| LNX-16 | Authorized vulnerability auditing | A | **Banshee** |
| LNX-17 | Network anomaly detection | A | **Banshee** |
| LNX-18 | Bluetooth and BLE discovery | A | **Banshee** |
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
| LNX-26 | Cell discovery | cell.tower.discovered | **Banshee** |
| LNX-27 | Cell handover | cell.handover | **Banshee** |
| LNX-28 | Cellular technology change | cell.technology.change | **Banshee** |
| LNX-29 | Cellular signal change | cell.signal.change | **Banshee** |
| LNX-30 | Bluetooth discovery | bluetooth.device.discovered | **Banshee** |
| LNX-31 | Network topology change | network.topology.change | **Banshee** |
| LNX-32 | Network anomaly | network.anomaly | **Banshee** |
| LNX-33 | Routing change | network.route.change | **Banshee** |
| LNX-34 | Geographical movement | location.change | **Banshee** |
| LNX-35 | Connectivity quality change | network.quality.change | **Banshee** |
| LNX-36 | Cellular registration change | cell.registration.change | **Banshee** |

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
| LNX-43 | Bee's Singularity Map integration | I | **Gwyn** — Bee found (github `chu4urdolen/bee`: a BT-tethered NanoPi NEO Air 2 field agent; Wi-Fi + GPS into `singularity.db`, fog-circle map). Proposed: Lynx tethers Bee over BT, sends her GNSS fixes to Bee's `/gps`, shows Bee's map summary on RADIO. Blocked on Lynx GNSS (no fix yet) and Tom's go for the pairing |

### E. Independent operation

| ID | Feature task | Class | Owner |
| --- | --- | --- | --- |
| LNX-44 | On-device offline intelligence | I | **Aria** |
| LNX-45 | Offline event journal and synchronization | I | **Aria** |
| LNX-46 | Remote inference failover | I | **Aria** |
| LNX-47 | Reflex inference priority | I | **Gwyn** — measured (docs/LNX-47-REFLEX-PRIORITY). Tom 2026-11-25: for now Lynx runs while Dushich is not running; no model change |
| LNX-48 | Noob communication discovery | A | **Banshee** |
| LNX-49 | Connectivity failure diagnosis and reporting | A | **Banshee** |
| LNX-50 | Radio capability registry | I | **Banshee** |

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
| LNX-60 | Service fingerprinting detection | I | **Banshee** |
| LNX-61 | TCP/UDP flood detection | I | **Banshee** (DONE: lynx_sense_security.py) |
| LNX-62 | Application-layer DoS protection | I | **Banshee** |
| LNX-63 | Exposed service vulnerability audit | O | **Gwyn** (DONE: lynx_exposure_audit.py) |
| LNX-64 | Kernel vulnerability audit | O | **Gwyn** — done (config audit, kernel) |
| LNX-65 | Stateful IPv4 and IPv6 firewall | I | **Aria** |
| LNX-66 | Network intrusion detection | I | **Banshee** (DONE: lynx_sense_security.py) |
| LNX-67 | SSH brute-force protection | I | **Aria** |
| LNX-68 | Cryptographic Nexus authentication | I | **Aria** |
| LNX-69 | Agent prompt injection protection | I | **Gwyn** — done, live (5f5fad1) |
| LNX-70 | Network resource exhaustion protection | I | **Aria** |
| LNX-71 | Unauthorized configuration change detection | I | **Banshee** |
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
| LNX-90 | Security event reporting to Aigel | I | **Banshee** |
| LNX-91 | Security incident synchronization with Argus | I | **Aria** |
| LNX-92 | Cellular inbound reachability assessment | O | **Aria** |
| LNX-93 | Upstream DDoS mitigation assessment | O | **Aria** |
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
| LNX-101 | Untrusted endpoint perception | security.endpoint.untrusted | **Banshee** |
| LNX-102 | Malicious message perception | security.message.suspicious | **Banshee** |
| LNX-103 | Resource exhaustion perception | security.resource.exhaustion | **Banshee** |

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
