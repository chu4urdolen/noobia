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

Run (a LAN service; port 112 is privileged; installed as supervised systemd service `aigel_intake.service`):

    # Installed via common/services/units/install_services.sh
    # Service definition: common/services/units/aigel_intake.service
    # Runner script: common/services/aigel_intake.sh

### Service Administration & Operations

```sh
# Check service status and recent journal logs:
sudo -n systemctl status aigel_intake.service
journalctl -u aigel_intake.service -f

# Verify API status:
curl -s http://127.0.0.1:112/api/v1/status | jq .

# Stop or restart:
sudo -n systemctl stop aigel_intake.service
sudo -n systemctl restart aigel_intake.service

# Rollback:
sudo -n systemctl stop aigel_intake.service
sudo -n systemctl disable aigel_intake.service
sudo -n rm /etc/systemd/system/aigel_intake.service
sudo -n systemctl daemon-reload
```

### Resource guardrails (queue #294, 2026-11-21)

`aigel_intake.service` (and `nexus_detect.service`) carry hard guardrails so
a busy or wedged service can never starve Qwen (18 GB VRAM in Ollama) or the
desktop:

| Key (in `[Service]`) | Value | Effect |
|---|---|---|
| `MemoryHigh=` | `768M` | kernel throttles allocation pressure |
| `MemoryMax=` | `1G` | hard cap; OOM-kill stays inside the unit's cgroup |
| `CPUQuota=` | `50%` | at most half a core |
| `SyslogIdentifier=` | `noobia-aigel` / `noobia-detect` | journal lines are greppable by name |
| `StartLimitIntervalSec=` / `StartLimitBurst=` (in `[Unit]`) | `60` / `3` | a crash loop is capped at 3 starts per 60 s, then the unit goes `start-limit-broken` instead of spinning |

Verify a running service's live limits:

```sh
CG=/sys/fs/cgroup/system.slice/aigel_intake.service
cat $CG/memory.max $CG/memory.high $CG/cpu.max    # 1073741824  805306368  50000 100000
journalctl -u aigel_intake -n 5 --no-pager          # lines tagged noobia-aigel[PID]
```

If a unit is `start-limit-broken` (see `systemctl is-failed aigel_intake`):
read `journalctl -u aigel_intake` for *why*, then clear and restart:

```sh
sudo -n systemctl reset-failed aigel_intake
sudo -n systemctl restart aigel_intake
```

Change or remove the guardrails in the unit **sources**
(`common/services/units/{aigel_intake,nexus_detect}.service`), then
`sudo -n bash common/services/units/install_services.sh`,
`sudo -n systemctl daemon-reload`, and restart the unit. Validate a unit
first with `sudo -n systemd-analyze verify <unit-file>`.

### Credentials & Security

All host secrets and tokens reside exclusively in `/noobia/aigel/private/` (mode 0700 dir, files mode 0600, excluded from Git):
- `intake_hosts.json`: per-host HMAC secrets and silence thresholds.
- `chat_token`: Bearer token guarding `POST /api/v1/chat`.
- `nexus_autonomy_secret`: local Nexus secret for the host autonomy harness.
- `lynx_autonomy_secret`: provisioned secret for the Lynx host autonomy harness (for Aria's IS-2 session).

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
