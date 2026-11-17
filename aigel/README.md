# Aigel — Nexus Nurse & Diagnostics

Aigel is the local nurse for Nexus: she passively monitors the health of the
hardware, software, and network, stores background samples, and reports
anomalies to the appropriate caretaker (Aria or Dushich).

## Layout

| Path            | What lives here                                                        |
|-----------------|------------------------------------------------------------------------|
| `config.json`   | Aigel's shared policy file (sampling cadence, GPU power limit)         |
| `tools/`        | Diagnostic/security tools (`nexus_net_guard.py`, `noob_lighthouse.py` + tests) |
| `AGENTS.md`     | Aigel's identity and working rules                                     |

The five Aigel health services (`cpu_report`, `net_report`, `disk_report`,
`mem_report`, `gpu_monitor`) are **not** in this directory: each has exactly
one script and one systemd unit in [`/noobia/common/services`](../common/services/)
with its unit sources in `common/services/units/`. See
[common/services/README.md](../common/services/README.md) for the sampling
schedule, arguments, stores, and install instructions.

## Monitoring model

* All monitoring is **passive** — Aigel never alters system settings unless
  explicitly instructed (the one deliberate exception is `gpu_monitor` pinning
  the GPU power limit to its 500 W policy at startup).
* Every service keeps a background store (see the common/services README),
  sampled 1 s for the first 5 min, then every minute until 1 h, then hourly
  until the next boot.
* Log entries should be written to `/noobia/aigel/logs/aigel.log` if it
  exists; otherwise, use standard output.
* Do not interfere with other agents' tasks unless a direct request is
  received.
