# Lynx Autonomous Health Heartbeat Telemetry Publisher

**Subsystem:** Remote Health Heartbeat & Telemetry Broadcast
**Platform:** OnePlus Nord 3 (`oplus6983_22823`)
**Author:** Banshee (Spirit of Initiative 💙)
**Date:** 2026-11-21
**Directory:** `lynx/tools/heartbeat/`

---

## 1. Overview & Protocol Specification

During untethered autonomous execution, human operators do not maintain interactive SSH sessions. To allow Nexus and the Noobian Council to monitor Lynx's physical status continuously and safely, Lynx broadcasts a structured, low-overhead health heartbeat telemetry packet every 60 seconds over UDP to Nexus (`192.168.100.106:4244`).

### 1.1 Telemetry Payload Schema

```json
{
  "node": "lynx",
  "platform": "OnePlus Nord 3 (CPH2493 / MT6983)",
  "uptime_sec": 3600,
  "battery": {
    "capacity_pct": 82,
    "voltage_mv": 7850,
    "current_ma": -420,
    "status": "discharging",
    "cell_delta_mv": 12
  },
  "thermal": {
    "shell_temp_c": 32.4,
    "soc_max_temp_c": 46.5,
    "status": "nominal"
  },
  "survival_policy": "NOMINAL_OPERATION",
  "watchdog": {
    "active": true,
    "timeout_sec": 30,
    "petting_interval_sec": 5
  },
  "cgroups": {
    "agent_mem_usage_mb": 142.5,
    "agent_mem_limit_mb": 512.0,
    "pressure_pct": 0.0
  },
  "timestamp": "2026-11-21T05:30:00Z"
}
```

---

## 2. Preflight Gate Implementation

The `lynx_heartbeat.py` tool provides:
1. Schema validation against incoming or staged telemetry payloads (`--validate <FIXTURE>`).
2. Synthesis of live telemetry packets when double-gated (`--live --allow-live`).
3. Payload serialization and emission verification (`--emit`).
4. Strict safety invariants: Read-only data collection, zero network packet spoofing, zero disk writes.
