# ARGUS: Historian, Archivist, Cartographer

**Noobia implementation backlog**  
**Prepared:** 2026-11-26  
**Status:** Revision 2, repository-verified where noted; live systems not modified  
**Target:** Raspberry Pi 5, Argon case, 1 TB NVMe, networked Codex CLI agent

## Mission and boundaries

Argus is Noobia's independent historian and cartographer. Dushich keeps **current Forge projects**, while Argus keeps **historical events, original evidence, archive copies, daily ledgers and radio maps**. Work is triggered by authenticated MCP requests; retries must be idempotent. No Noob's project ownership or conversation continuity should be transferred to Argus.

**Permission requirement:** Argus has full local CLI execution and `NOPASSWD:ALL`, with trust boundaries at network ingress. MCP exposes named, authenticated tasks, not an unauthenticated root shell. The existing Council bridge is read-only by design, distinct from Argus's new privileged local agent runtime.

**Data policy:** immutable source evidence + append-only event ledger; separately versioned summaries and computed map estimates. Private coordinates, MAC addresses and Council credentials must not appear in public repos. Store internal UTC timestamps and render local calendar days in `Europe/Sofia`.

**Priority:** P0 bootstraps operation, P1 core responsibilities, P2 later improvements.

## Verified repository starting points

- `common/AGENTS.md` shared instructions and role conventions.
- `council/README.md` lists Argus at `192.168.100.105`, human port `47200`, AI port `47201`; Council bridge is separate from MCP.
- `common/mcp/` is the established Noobia MCP system.
- `common/tools/forge_db.py` has `forge-db changes --since`, `project_notes` and `project_notes_archive`; the **published code does not define `projects_archive`**. Confirm live DB migrations.
- `dushich/coding/dushich_summarizer.py` powers `dushich-summarizer` on Nexus.
- `docs/noobs/ARGUS.md` points to `argus/services`, `argus/tools`, `argus/tests`, `argus/web`.
- Bee repository (`chu4urdolen/Bee`, master): verified `gps/estimate_heatmaps.py`, `gps/render_world_map.py`, `web/server.py`, and `web/map.html`. The default live database is `/data/singularity.db`, table `wifi_obs`; actual database contents and any environment override require live verification.
- Argus repository (`chu4urdolen/argus`, master): existing `argus-backup.sh`, `argus-scans.sh`, `argus-scans-parser.py`, `argus-scan-guard.sh`, `argus-temp-guard.py`, `services/`, `tools/`, and `web/server.py`. Audit and reuse before adding duplicate services.
- Lynx reference runtime (`noobia/lynx/tools/agent/`): `lynx_agent.py`, `lynx_agent_queue.py`, `lynx_agent_worker.py`, `lynx_agent_health.py`, `lynx_codex_tool.py`, `lynx_tool_broker.py`, `deploy_native_mcp_catalog.py`, `brain.json`. Adapt these patterns for the Raspberry Pi and network-driven inputs; inspect dependencies rather than blindly copying phone-specific code.
- Repository-visible journals include `aria/JOURNAL.md`, `dushich/JOURNAL.md`, and `gwyn-app-nub/JOURNAL.md`; discover all additional live journals.
- Argus's exact Council persona file and live Forge schema remain unverified; discover before implementation.

Repository sources:
- https://github.com/chu4urdolen/noobia
- https://github.com/chu4urdolen/Bee
- https://github.com/chu4urdolen/argus
- https://github.com/chu4urdolen/Bee/blob/master/gps/estimate_heatmaps.py
- https://github.com/chu4urdolen/Bee/blob/master/web/server.py
- https://github.com/chu4urdolen/noobia/tree/main/lynx/tools/agent
- https://raw.githubusercontent.com/chu4urdolen/noobia/main/common/AGENTS.md
- https://raw.githubusercontent.com/chu4urdolen/noobia/main/common/tools/forge_db.py
- https://raw.githubusercontent.com/chu4urdolen/noobia/main/common/mcp/README.md
- https://raw.githubusercontent.com/chu4urdolen/noobia/main/council/README.md

## Work items

### EPIC A: Computer, Codex, and Autonomy

| ID | Priority | Task | Acceptance criteria |
|---|---|---|---|
| ARG-001 | P0 | Audit Raspberry Pi installation | Document OS, accounts, packages, services, network, boot status, Git checkout and disk inventory. |
| ARG-002 | P0 | Verify 1 TB NVMe | Mount and verify persistent storage with no destructive formatting; test reboot persistence. |
| ARG-003 | P0 | Harden Raspberry Pi OS | Review updates, SSH, firewall, logging, service exposure, and recovery access. |
| ARG-004 | P0 | Configure passwordless sudo | Argus account supports sudo -n for arbitrary local commands; validate sudoers syntax. |
| ARG-005 | P0 | Verify/install Codex CLI | Working authenticated interactive and noninteractive invocations; reuse existing installation where possible. |
| ARG-006 | P0 | Configure full Codex permissions | Argus agent has full local execution/approval policy; test its actual effective permissions. |
| ARG-007 | P0 | Recover historical personality | Find Argus persona in Council/earlier files, write argus/AGENTS.md, inherit common/AGENTS.md. |
| ARG-008 | P0 | Persistent agent runtime | Adapt Lynx agent/queue/worker/health/Codex patterns; start and supervise independent Argus Codex agent with durable session/task state. |
| ARG-009 | P0 | MCP integration | Authenticated Noobs can call named Argus tools and get bounded results. |
| ARG-010 | P1 | Council bridge integration | Preserve Argus Council identity and enable turn-based dialogue without conflating Council and full-power agent. |
| ARG-011 | P1 | Queue and job history | Prevent overlapping incompatible tasks and expose job IDs, status, and historical outcomes. |
| ARG-012 | P2 | Agent health and recoverability | Detect faults, checkpoint state, and recover without autonomous reboot loops. |

### EPIC B: Journals, Events, and Daily Ledger

| ID | Priority | Task | Acceptance criteria |
|---|---|---|---|
| ARG-013 | P0 | Journal source discovery | Start with Aria, Dushich and Gwyn journals visible in Git; enumerate all live JOURNAL.md paths per Noob and host; record verified access routes. |
| ARG-014 | P0 | Network journal collector | Retrieve from registered sources without modifying source files. |
| ARG-015 | P0 | Incremental synchronization | Use source identifiers, file hashes and cursors; repeat calls are idempotent. |
| ARG-016 | P0 | Original evidence retention | Preserve source versions with content hashes, path, author/source, captured time and original time. |
| ARG-017 | P1 | Forge daily changes feed | Fetch projects, notes, and paths since last checkpoint via forge-db changes --since. |
| ARG-018 | P1 | Historical event extraction | Convert source statements and project changes to timestamped typed events with citations. |
| ARG-019 | P1 | Noob attribution | Distinguish actor, project owner/recipient, collaborators, and affected project. |
| ARG-020 | P1 | Summarizer reuse | Reuse dushich-summarizer for long source material, retaining originals and provenance. |
| ARG-021 | P1 | Daily ledger generator | Build human-readable ledger per Europe/Sofia calendar day with chronology, achievements and blockers. |
| ARG-022 | P1 | MCP collection trigger | One argus_collect_day call executes pickup, archive sync, extraction and ledger production. |
| ARG-023 | P1 | Historical query MCP tools | Query by day, Noob, project, event and source record; return evidence links. |
| ARG-024 | P2 | Milestones | Highlight independently confirmed project milestones while keeping routine events. |
| ARG-025 | P2 | Late additions and corrections | Append new evidence and version daily summary; never silently rewrite old evidence. |

### EPIC C: Forge Archive and Database

| ID | Priority | Task | Acceptance criteria |
|---|---|---|---|
| ARG-026 | P0 | Initialize Argus SQLite | Create indexed historical DB on NVMe with migration/versioning. |
| ARG-027 | P0 | Register source feeds | Track source owners, addresses, trust boundaries, cursors and last successful ingestion. |
| ARG-028 | P1 | Backfill Forge notes | Import all available projects, project_notes and project_notes_archive with original IDs. |
| ARG-029 | P1 | Incremental Forge archive mirror | Sync archived notes by stable ID and hash, independent of active notes changes. |
| ARG-030 | P1 | Project state history | Store each observed project-version snapshot and timestamp with change details. |
| ARG-031 | P1 | Archive through Forge CLI | Safely expose existing forge-db note archive operation, observing project ownership. |
| ARG-032 | P1 | Compact project spec | Use summarizer to draft concise current project synopsis without losing archived notes. |
| ARG-033 | P1 | Archive-before-delete guard | No move/delete until target archive and Argus ingest are verifiably committed. |
| ARG-034 | P1 | Timestamped search | Index events and notes by occurred_at, captured_at, Noob, project and type. |
| ARG-035 | P2 | Backup and restore | Consistent versioned SQLite snapshots plus off-device verified recovery; do not rely on existing rsync --delete mirror as historical backup. |
| ARG-036 | P2 | Cross-references | Link Council decisions, journal entries, Forge notes and project milestones. |

### EPIC D: Singularity Cartography

| ID | Priority | Task | Acceptance criteria |
|---|---|---|---|
| ARG-037 | P0 | Find Bee map repo and DB | Source and renderer verified in Bee repo; confirm live /data/singularity.db (or BEE_SINGULARITY_DB override), wifi_obs schema, contents, and backup/export path. |
| ARG-038 | P0 | Inspect Lynx mapping tools | Verify actual GPS/RSSI tooling and safe observation interfaces without cellular reconfiguration. |
| ARG-039 | P1 | Common radio observation schema | Record observer, timestamp, radio type, BSSID/MAC, SSID, RSSI, GNSS fix/accuracy, frequency and batch ID. |
| ARG-040 | P1 | Bee offload | Pull offline Bee observations into Argus on trusted network with acknowledgements. |
| ARG-041 | P1 | Lynx offload | Pull offline Lynx observations without disrupting cellular persistence. |
| ARG-042 | P1 | Immutable observation archive | Store received raw observation batches with source authenticity and hashes. |
| ARG-043 | P1 | Cross-source deduplication | Unique IDs and upsert guards handle retries from both producers. |
| ARG-044 | P1 | Import old Singularity map | Migrate or adapt existing Bee map data with no loss and traceable source. |
| ARG-045 | P1 | RSSI estimator port | Port verified gps/estimate_heatmaps.py overlapping-disk estimator with strict-min and quantile fallback; compare fixture results; adapt source filter and collector calibration for Lynx. |
| ARG-046 | P1 | Update transmitter map | Recompute position estimates from new samples and version old estimates. |
| ARG-047 | P1 | Uncertainty metrics | Maintain radius_m, score, mode, n_used, GPS accuracy and estimator version; label heuristic scores/radii rather than calibrated confidence. |
| ARG-048 | P1 | Cartography MCP tools | Expose map import/recalculate/lookup/stats/export/status with authenticated callers. |
| ARG-049 | P2 | Existing map frontend | Reuse Bee visuals and map controls after establishing current source of truth. |
| ARG-050 | P2 | Map statistics | Count observations/transmitters/new BSSIDs/coverage and show quality metrics. |
| ARG-051 | P2 | Radio outlier checks | Account for random MACs, mobile transmitters, poor GNSS, duplicated BSSIDs and RSSI outliers. |

### EPIC E: Security and Operations

| ID | Priority | Task | Acceptance criteria |
|---|---|---|---|
| ARG-052 | P0 | Stable LAN identity | Confirm DHCP reservation/IP 192.168.100.105 and network reachability. |
| ARG-053 | P0 | SSH hardening | Working key-only authentication, restricted ingress and physical recovery path. |
| ARG-054 | P0 | Firewall policy | Allow only needed SSH, Council and MCP trusted sources; no WAN exposure. |
| ARG-055 | P0 | Authenticated MCP access | Implement verified peer identity, bounded operations and replay protection. |
| ARG-056 | P0 | Treat inputs as untrusted | Journal/map text cannot authorize arbitrary execution; validate file paths and payloads. |
| ARG-057 | P1 | Systemd supervision | On-boot services, bounded retries, restart state, health endpoint. |
| ARG-058 | P1 | Audit trail | Durable logs for tool calls, sudo activity and archival operations, with redaction. |
| ARG-059 | P1 | Off-device backup | Check consistent backups and documented restoration procedure. |
| ARG-060 | P1 | Health telemetry | Audit/reuse existing argus-temp-guard and scan-guard services; log storage state, temps, network status and critical services. |
| ARG-061 | P2 | Argon case checks | Verify button, fan and shutdown integration on live hardware. |
| ARG-062 | P2 | External power guardian study | Revisit Naeturblom/RP2040 I2C design, separate from historian MVP. |
| ARG-063 | P2 | Outage recovery | Recover incomplete transfers, imports, and notes compaction after power/network loss. |

### EPIC F: Validation and Release

| ID | Priority | Task | Acceptance criteria |
|---|---|---|---|
| ARG-064 | P1 | Daily ledger end-to-end test | Multiple source feeds produce a correct, cited daily ledger from one MCP call. |
| ARG-065 | P1 | Archive reconstruction test | Retrieve evidence from Argus after Forge active notes are compacted/moved. |
| ARG-066 | P1 | Cross-device map test | Bee and Lynx samples merge into one estimated location with confidence/uncertainty. |
| ARG-067 | P1 | Idempotency test | Repeated ingestion produces no duplicates and stable summary versions if no new input. |
| ARG-068 | P1 | Offline test | Nexus/Bee/Lynx outages do not corrupt Argus and retries recover on reconnection. |
| ARG-069 | P1 | Reboot test | Persistence of agent identity, sessions, cursors, ledgers and map DB verified. |
| ARG-070 | P1 | Docs and Noobia integration | Update argus/ and docs/noobs/ARGUS.md; register MCP tools, schema and backup instructions. |

## MCP contract proposal

| Tool | Input | Action/output |
|---|---|---|
| `argus_collect_day` | `date?`, `force?` | Pull journals, Forge changes and archive; update event ledger and daily summary; return job ID/result. |
| `argus_sync_status` | `source?` | Last checkpoint and per-source success/error details. |
| `argus_daily_ledger` | `date` | Return dated versioned ledger with evidence references. |
| `argus_search_history` | `query`, `from?`, `to?`, `noob?`, `project?` | Structured matches with cited raw-source IDs. |
| `argus_forge_archive` | `project`, `upto_note_id?`, `move?` | Archive only via Forge interface; guard movement on verified persistence. |
| `argus_map_import` | `source`, `batch_ref` | Ingest signed/hash-checked batch; report inserted/duplicate/error counts. |
| `argus_map_recalculate` | `scope?` | Recompute positions/uncertainty without erasing observations. |
| `argus_map_lookup` | `bssid` | Coordinates, radius, samples, last observed and provenance. |
| `argus_map_statistics` | `period?` | Map coverage and collection counts. |
| `argus_map_export` | `format`, `scope?` | Private by default; public output must be redacted/coarsened. |

For long operations, return immediately with a job ID, then allow `argus_job_status` and `argus_job_result`; do not block MCP until summarization finishes. Scheduled automatic collection is optional, disabled initially. The on-demand MCP trigger is the acceptance path.

## History schema outline

`argus.db`: `sources`, `raw_records`, `events`, `event_participants`, `forge_history`, `forge_archive`, `daily_ledgers`, `milestones`, `sync_checkpoints`.

Minimal event fields: `event_id`, `occurred_at` (source event UTC), `recorded_at` (ingest UTC), `source_id`, `source_record_id`, `actor`, `recipient`, `project`, `event_type`, `description`, `summary`, `evidence_hash`.

`singularity.db`: `collectors`, `imports`, `observations`, `transmitters`, `estimated_positions`, `position_history`. Each raw observation should include `observer`, source event timestamp, `radio_type`, BSSID/MAC, SSID if available, RSSI dBm, scanner GPS coordinates and accuracy, frequency/channel when available, stable observation/batch IDs. Scanner coordinates are not asserted transmitter coordinates. Store estimates, uncertainty radius and estimator version separately.

## Bee implementation (verified repository, live DB pending)

Bee historically received OwnTracks GPS fixes from Dushich's Nokia X30 5G over BT tether and scanned Wi-Fi via `iw`. The current repository confirms `web/server.py` handles GPS ingest and Wi-Fi observation storage. The default `BEE_SINGULARITY_DB` is `/data/singularity.db`; `wifi_obs` records `mac, ssid, ts, lat, lon, rssi_dbm, rssi_pct, src, iface, scan_src`. Retrieve a consistent SQLite snapshot from Bee; do not assume the default path is the live configuration.

`gps/estimate_heatmaps.py` selects observations with `scan_src='iw'`, groups by MAC and SSID, ranks RSSI to assign disk radii, then searches a local meter grid for maximum strict overlap (minimum disk score). If strict overlap fails, it uses a quantile fallback. The half-maximum region gives a heuristic radius. Defaults include strongest fraction 0.35, minimum 8 samples, radii 8–80 m, grid step 3 m, maximum grid side 220, fallback quantile 0.20. Preserve these as baseline configuration, not scientifically calibrated distances. Output `heatmaps/summary.json` has `mac, ssid, lat, lon, radius_m, score, mode, n_used`. `gps/render_world_map.py` and `web/map.html` provide the existing visualization.

For integration, preserve raw rows, add stable collector/source IDs, adapt the estimator's `scan_src` filter to validated Lynx observations, and compare outputs against Bee fixtures before switching. Check for receiver-specific RSSI bias and use conservative estimates. Only map authorized stationary infrastructure; do not track people or mobile devices. Lynx observes radio/GPS without autonomously changing cellular registration, APN, SIM or persistent connectivity. The live Singularity database is not present in the repository tree and must be obtained from Bee.

## Existing Argus services and Lynx runtime

Audit the live Argus checkout against both repository trees. Reuse backup, scanning, temperature, scan supervision, fan and web services as applicable. The existing `argus-backup.sh` mirrors directories using `rsync --delete` to `/mnt/nvme/backups/`; retain ordinary mirroring where appropriate but separate historical snapshots, with version retention and off-device restoration tests.

Use Lynx's agent entry point, durable queue, worker, health monitoring, Codex adapter, tool broker, MCP catalog deployment and brain configuration as reference implementations. Keep Argus's own conversation and task state. Verify live permission policy and systemd settings (including any NoNewPrivileges restrictions) rather than assuming CLI access implies sudo works within the agent service.

## Suggested rollout and dependencies

1. **Foundation:** ARG-001..009, 026..027, 052..056. Confirm boot/storage and effective root permissions before network exposure.
2. **Historian MVP:** ARG-013..023, 028..030, 034, 064, 067. One MCP ping creates a sourced daily ledger.
3. **Archive ownership:** ARG-031..033, 035..036, 065. Migrate repetitive Forge archiving only after verified backfill.
4. **Cartography:** ARG-037..048, 066. Bee source is located; verify/export live database first; both collectors offload offline captures into Argus.
5. **Polish and resilience:** remaining P1/P2 items, tests, system health and optional external power guardian.

## Risks and live-system checks

- The published Forge archive table is `project_notes_archive`, **not** a projects table clone; live schema might differ. `changes --since` currently excludes archive updates. Extend its interface or add a cursor-based archive feed.
- Collecting arbitrary `JOURNAL.md` content with an unrestricted Codex CLI creates prompt-injection risk. Never treat ingested text as tool policy/authorization; separate parsing from actions.
- Do not expose MCP or unrestricted root execution to WAN. Restrict peer identity and ingress, audit invocations, store keys out of Git, and verify permission changes from a recovery session.
- Prefer original RSSI estimator first; do not claim precise AP location from single RSSI readings. Handle GNSS error, BSSID randomization and moving transmitters.
- Historic microSD boot failures were previously reported; audit boot chain and possible NVMe migration without altering the 1 TB data partition.
- Preserve original Council identity/personality, existing Git layout, independent agent conversation and documented no-bricking shutdown policy.

## End-to-end demonstration

One authenticated `argus_collect_day` call retrieves multiple journals, current Forge changes and archived notes; stores originals; produces a chronological ledger and source-backed summary; repeated calls preserve idempotency; after restart the exact history remains searchable. Separately, Bee and Lynx submit observations offline-to-online, Argus merges data and the existing Singularity Map shows updated estimated positions and uncertainty.
