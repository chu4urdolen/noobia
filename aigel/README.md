# Aigel — Nexus Nurse & Diagnostics

Aigel is the local nurse for Nexus: she passively monitors the health of the
hardware, software, and network, stores background samples, and reports
anomalies to the appropriate caretaker (Aria or Dushich).

## Layout

| Path            | What lives here                                                        |
|-----------------|------------------------------------------------------------------------|
| `config.json`   | Aigel's shared policy file (sampling cadence, GPU power limit)         |
| `tools/`        | Diagnostic tools + tests: `aigel_vitals.py` (vitals board), `aigel_sentinel.py` (threshold alerts), `aigel_dmesg_scout.py` (kernel scout), `noob_lighthouse.py` (LAN beacon), `nexus_net_guard.py` (net audit) |
| `AGENTS.md`     | Aigel's identity and working rules                                     |
| `codex-aigel`   | Codex wrapper: separate Codex home, pinned local Ollama model          |
| `launch`        | tmux launcher (socket `aigel-clean`, `--detached`/`--attach`/`--resume`)|
| `private/`      | Aigel's Codex home (`private/codex`) and conversation registry; not in Git |
| `logs/`         | Aigel's log store: `aigel_sentinel` appends `ALERT` lines to `aigel.log` |

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
  exists; otherwise, use standard output. `aigel_sentinel` follows exactly
  this convention for its `ALERT` lines.
* The Lighthouse LAN roster is a shared config at
  [`/noobia/common/lighthouse_roster.json`](../common/lighthouse_roster.json);
  onboarding a new LAN inhabitant is a one-line edit there.
* Do not interfere with other agents' tasks unless a direct request is
  received.

## Launcher

Aigel started on 2026-11-18 by Noob's instruction as an active diagnostics
agent, running like Solo Dushich: Aria's Unix authority, a separate Codex home
at `private/codex`, and local Ollama `qwen3.8:27b` on the Nexus RTX 5090
(`--oss --local-provider ollama`, no cloud models).

```sh
# Start a fresh conversation in the background:
/noobia/aigel/launch --detached

# Attach to a running conversation:
tmux -L aigel-clean attach-session -t noobia-aigel-<ID>

# Resume an earlier conversation:
/noobia/aigel/launch --resume <ID>
```

Conversation IDs are registered in `private/conversations.json` (mode 0600),
excluded from Git. Aigel is passive by role: she reads, samples, and reports
anomalies to Aria or Dushich; she does not alter system settings without an
explicit instruction.
