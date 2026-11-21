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

## Autonomy service (A1, A2, A4, A6 - 2026-11-21)

Aigel's role in Noobia's autonomy engine (contract:
[`common/autonomy/ARCHITECTURE.md`](../common/autonomy/ARCHITECTURE.md),
plan: [`common/autonomy/PLAN.md`](../common/autonomy/PLAN.md)). She is the
nurse angel between a machine's senses and its Noob: hosts POST her the
chunks they cannot explain, she decides, and people can watch and talk to
her. She describes the world; she never commands hardware.

| File                      | Role |
|---------------------------|------|
| `service/aigel_intake.py` | A1: intake on Nexus - `POST /api/v1/chunk`, per-host HMAC or Bearer auth from the private registry, bounded; her decision **is** the HTTP reply |
| `service/aigel_think.py`  | A2 (+A6): thinking step on Qwen (local Ollama queue): JSON `quiet`/`message` + structured `patterns` + `priority_rules`; plus the A4 chat turn |
| `service/aigel_web.py`    | A4: the web page for a Noob - host status, recent chunks and decisions, talk to Aigel (`POST /api/v1/chat`) |
| `service/aigel_log.py`    | bounded one-line writer to the `noobia-aigel` view |
| `private/intake_hosts.json` | per-host secrets (gitignored, never in Git) |

Run (a LAN service; port 112 is privileged - the install is Aria's step,
IS-3):

    python3 aigel/service/aigel_intake.py --port 112 \
        --hosts aigel/private/intake_hosts.json --chat-token <token>

The chat endpoint (`POST /api/v1/chat`) is **disabled until a
`--chat-token` / `AIGEL_CHAT_TOKEN` is configured** (honest 503), and
with a token it is Bearer-authenticated and capped (1 turn / 2 s,
60 turns / hour) so the shared single Qwen queue stays usable (Gwyn
review #255).

Tests: `cd /noobia && python3 -m unittest discover -s aigel/service -p 'test_*.py'`
(70 tests). The wire format is pinned cross-component by
`common/autonomy/test_integration_aigel.py`.

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
