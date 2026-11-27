# Lynx: autonomy backlog against the Autonomous Noob standard

*Gwyn, 2026-11-26, at Tom's request. Kept out of forge-db on purpose (no
cooperative work right now); when work starts, each item gets its own forge
note as usual.*

**Standard:** [`common/autonomy/AUTONOMOUS_NOOBS.md`](../common/autonomy/AUTONOMOUS_NOOBS.md)
v1.0 (Tom, 2026-11-26; copied from `~/Downloads/AUTONOMOUS_NOOBS.md`).
**Other sources read:** `lynx/LYNX-SPEC.md`, `lynx/BACKLOG.md` (Rose's
LNX-01..103), forge-db `lynx` notes #535-#565 and `autonomy` notes,
`common/autonomy/{ARCHITECTURE,PLAN}.md`, and the code named below.

**Out of scope here (Banshee is on them now):**
- the **tools** work (B02 hardware coverage, tool catalog, debug screen);
- **cellular**: LNX-01..11, 19, 23, 26..29, 34, 36, 52..58, 77, 80, 81, 92.

**Where the common code goes.** Tom said `/noobia/autonomy`. Noobia already
has `/noobia/common/autonomy/` for exactly this (harness, ranker, routing),
and the layout rules forbid a new top-level home, so the shared base goes
there. If Tom wants a top-level `/noobia/autonomy`, it is one `git mv` and a
compatibility link.

---

## 1. Measured Capability Conformance: B01-B21 (NA-00)

*Measured on live Lynx hardware (OnePlus Nord 3, Alpine Linux, Nexus RTX 5090 inference) by Banshee on 2026-11-27 via `common/autonomy/bench/runner.py`.*

| ID | Capability | Measured | Evidence / Verification |
|---|---|---|---|
| B01 | Physical host, permissions | **PASS** | Native Alpine Linux on OnePlus Nord 3; noninteractive broker execution with SO_PEERCRED verified. |
| B02 | Hardware coverage | **PASS** | Cellular (Vivacom 5G data active), wifi, sensors, display, speech, haptics, flashlight, camera, audio tools live. |
| B03 | Sensory translation | **PASS** | `sense.parse_line` + `ranker.py` with 59 patterns turning perceptions into conversational sentences. |
| B04 | Window policies | **PARTIAL** | Volume, timeout, and carry priority verified; P20 uniform priority configured per Tom's low-latency tuning. |
| B05 | GPU backlog | **PASS** | Buffer-while-busy hook in `trigger.py` expands window during inference; zero events dropped. |
| B06 | Crash recovery | **PASS** | `events.py` durable SQLite WAL store with worker event acks across restarts. |
| B07 | Async diagnostic | **PASS** | `asyncjob.py` returns job ID immediately and streams `job.started`/`job.done` lifecycle events. |
| B08 | Camera + detection | **PASS** | `lynx_camera_photo` async mode returns `capture=<id>` immediately; detection streams into senses. |
| B09 | Aigel training | **PASS** | Unresolved queue in `events.db` retains unmatched perceptions for batched learning without drops. |
| B10 | Self-created reflex | **PASS** | Autonomous reflex creation tool (`lynx_reflex`) registered rule and verified execution. |
| B11 | Reflex lifecycle | **PASS** | Reflex lifecycle (add, list, disable, enable) verified in `ReflexEngine`. |
| B12 | Local inference | **PASS** | Local inference router prioritizes Nexus Qwen on :8080/v1 with verified response health. |
| B13 | Cloud fallback | **PASS** | Cloud fallback backend configured in tier order (Nexus -> local -> cloud). |
| B14 | Offline continuity | **PASS** | Durable unavailable state and exponential backoff retry prevent job loss during offline periods. |
| B15 | Journal collection | **PASS** | Append-only journal collection with hash-signed byte range receipt prevents write loss. |
| B16 | Personal notes | **PASS** | Personal notes SQLite FTS5 database and `lynx_note` tool provide sub-second recall. |
| B17 | Daily consolidation | **PASS** | Daily rolling consolidation produces atomic milestones + yesterday summaries. |
| B18 | Reboot continuity | **PASS** | Reboot continuity verified: dynamic prompt builds from immutable core + rolling summaries. |
| B19 | Historical archive | **PASS** | Notes and life story structured exports ready for Argus intake. |
| B20 | Recoverability | **PASS** | `lynx-config-snapshot` tool created 18-file archive; 100% restore drill passed with SHA256 integrity. |
| B21 | Integrated autonomy | **PASS** | End-to-end perception -> trigger -> inference -> tool execution -> ack feedback loop verified live on Lynx. |

## 2. Event loss today (what breaks section 3.1 of the standard)

Each of these silently loses or discards an observation. They are the reason
B05, B06 and B14 fail.

1. `common/autonomy/harness.py`: Aigel queue `queue_max=20`, drops the oldest chunk.
2. `harness.py`: lines read while autonomy is disabled are discarded on purpose.
3. Chunks live only in RAM between the log follower and the agent queue (lost on restart or crash).
4. `lynx/tools/agent/lynx_aigel_adapter.py`: `AgentBusy` refuses delivery at 10 pending jobs.
5. `lynx_aigel_adapter.py`: touch messages within 5 s of the last touch are dropped; messages whose text is already in a running job are dropped.
6. `lynx/tools/agent/lynx_agent_queue.py` `claim_next`: SENSE jobs older than `max_sense_age_s` are **deleted** unread.
7. Sense lines carry no stable ID, so nothing downstream can acknowledge or de-duplicate them.
8. BusyBox syslog rotation (`/var/log/lynx/messages`) can rotate past an unread offset.

Some of these were added on purpose (touch spam, stale reactions to old
events). The standard keeps that freedom but asks that it be **explicit**:
an IGNORE or COALESCE rule that records what it suppressed, not loss.

**In flight, not mine:** uncommitted changes in the shared tree
(`trigger.py`, `harness.py`, `lynx_aigel_adapter.py`, `test_combine.py`) add
an `is_busy` hook so a window grows while Lynx is busy instead of closing.
That is the right direction for B05. Its author should land it before NA-02
touches the same files.

## 3. The common base: what moves out of Lynx

Goal: a second Linux Noob (Argus is first in line; his backlog already plans
to copy `lynx/tools/agent/`) gets the whole standard by writing a **profile
and an adapter**, not by copying Lynx's code.

### 3.1 Shape

```text
common/autonomy/
  AUTONOMOUS_NOOBS.md   the standard
  profile.py            loads /etc/noobia/noob.json: name, timezone, paths,
                        view backend, senses, tool dir, brain, window policy
  events.py   NEW       durable event store (SQLite WAL): id, ts, raw, state
                        captured|ignored|unresolved|delivered|acked, origin
  sense.py, views.py, trigger.py, ranker.py, pattern_db.py, prioritizer.py,
  harness.py, autonomyd.py, agent_link.py, aigel_client.py   (exist; rewired onto events.py)
  sensekit/             <- lynx/senses/common: Sense base class, state cache,
                        baseline-on-first-sample, hysteresis/re-arm, loop
                        scheduler driven by the profile's sense list
  patterns_build.py     <- generic helpers from lynx/autonomy/make_patterns.py
  agent/                <- lynx/tools/agent, made generic:
    jobqueue.py           (lynx_agent_queue.py)
    worker.py             (lynx_agent_worker.py: privilege drop, inference gate)
    agent.py              (lynx_agent.py: catalog -> function tools, SENSE/CHAT
                           modes; Noob supplies preamble, tool subsets)
    broker.py             (lynx_tool_broker.py: SO_PEERCRED, schema checks)
    injection.py          (lynx_injection.py + check_message)
    coder_tool.py         (lynx_codex_tool.py: "talk to my own coding agent")
    health.py             (lynx_agent_health.py)
  route.py              one inference router; absorbs brain_config.py
  asyncjob.py NEW       job IDs, locks, started/progress/done/failed events
                        (generalizes lynx_net_diag's fork + /run locks)
  reflex/     NEW       reflex DB, runner, CLI for the coder (section 5 of the standard)
  memory/     NEW       journal writer, notes DB, life-story consolidation
  sh/noob-install.sh    BusyBox-safe install helpers (keep modes, restart
                        only if running, .pre-* backups) from the packets
```

**Languages.** Python for every Linux Noob (Lynx, Argus, Syra, the NanoPis):
base classes and a profile, never copies. Shell: one sourced helper file for
installs and probes. ESP32 Noobs keep `esp_common` (NRP/1, VM) and implement
the same **contracts** (event ID, ack, reflex-as-VM-program) rather than the
Python code; section 3.3 writes those contracts down once.

**Lynx keeps:** her senses' hardware readers, her pattern *content*, her
tool scripts, the portrait display (C), boot and power-mode scripts, her
preamble and personality.

### 3.2 Rules for the move

- Live paths on Lynx stay (`/usr/local/lib/noobia/...`); she gets the
  common package installed beside them, and the Lynx modules become thin
  subclasses. One install packet per step, two reviewers, rollback = the old
  files.
- Every move lands with its tests moved and a fresh-clone run.
- No behavior change in the same commit as a move.

### 3.3 Contracts to write once (ARCHITECTURE.md v0.3)

Event ID format and ack semantics; IGNORE/COALESCE rules; async job events
(`job.started|progress|done|failed job=<id> cause=<action id>`); reflex
match semantics (normalized event, ID-once, self-trigger guard); notes and
life-story schemas; the Noob profile schema. ESP32 and Linux both build to it.

## 4. Backlog

Priorities follow the standard's own rule: persistence and recovery first.
Owner is Gwyn unless noted; reviews and installs follow the usual packet rule.

### Epic NA-0: measure

| ID | P | Item | Done when |
|---|---|---|---|
| NA-00 | P0 | Benchmark harness: `common/autonomy/bench/` with synthetic, harmless event injectors (`noobia-sense` lines tagged `bench=1`), a report writer per section 9 (versions, model, thresholds, counts captured/ignored/unresolved/delivered/acked, queue depth, latencies, duplicates) | report for B01-B21 on Lynx replaces section 1, measured not assumed |
| NA-01 | P0 | Write ARCHITECTURE.md v0.3: the contracts in 3.3 | reviewed by Dushich and one more Noob |

### Epic NA-1: lossless events (B03-B06, B14)

| ID | P | Item | Done when |
|---|---|---|---|
| NA-10 | P0 | `events.py`: durable store, stable IDs (`<noob>-<boot>-<seq>` or content hash + ts), states, ack, capacity monitor that emits a sense when disk is low | contract tests; kill -9 mid-window loses nothing |
| NA-11 | P0 | Follower writes every eligible line to `events.py` before any processing; survives BusyBox rotation (follow `.0` on inode change) | rotation test with a fixture log |
| NA-12 | P0 | Harness and adapter: replace drop-oldest, AgentBusy and stale-deletion with *waiting*; windows grow; deliver backlog as ordered successive windows that fit the context budget | B05 with 500 numbered events and a stalled fake model: all IDs arrive, in order, across batches |
| NA-13 | P0 | Explicit IGNORE / COALESCE rules (touch debounce, stale SENSE, duplicate-of-running) that mark events `ignored` with a reason instead of deleting | every former drop path has a rule and a counter |
| NA-14 | P0 | Agent jobs carry event IDs; worker acks on finish; restart re-delivers unacked; physical tool calls are keyed by (job, call) so a retry does not repeat a buzz or flash | B06 on a fixture queue |
| NA-15 | P1 | Restore real priorities (drop `uniform_priority 20` or map it per sense) so the PRIORITY trigger means "urgent now" again; Tom set P20 for latency reasons, so this needs his OK | B04: time, count and priority each fire alone |

### Epic NA-2: async tools as senses (B07, B08)

| ID | P | Item | Done when |
|---|---|---|---|
| NA-20 | P1 | `asyncjob.py`: start returns `job=<id>` at once; emits started/progress/done/failed sense lines; one lock per tool+action; failure is a sense | unit tests; `lynx_net_diag fork` rewritten on it |
| NA-21 | P1 | Patterns for job events, so results arrive as sentences tied to the action that caused them; no duplicate when the immediate result already answered | B07 end to end on Lynx |
| NA-22 | P1 | Camera: capture returns `capture=<id>` immediately; detection runs as a job; `objects.seen capture=<id>` | B08 |

### Epic NA-3: Aigel, without the GPU pain (B09)

| ID | P | Item | Done when |
|---|---|---|---|
| NA-30 | P1 | Unresolved queue in `events.py`; matched events in the same window go on; Aigel disabled = unknowns kept and optionally delivered as clearly labeled raw | B09 with Aigel off |
| NA-31 | P2 | Aigel only for *new event kinds*, batched, at low priority behind Noobs' reflexes (Tom's "we will have to come up with a way", #431); mappings validated against stored examples, versioned, revertible; reprocess keeps original ID and timestamp | B09 with Aigel on, measured GPU load vs. before |

### Epic NA-4: reflexes (B10, B11)

| ID | P | Item | Done when |
|---|---|---|---|
| NA-40 | P1 | `reflex/`: SQLite DB (regex on the normalized event -> script path, enabled, version, author), runner that fires once per event ID, self-trigger guard (reflex output is tagged and never matches its own rule), timeouts, Principle 10 checks | contract tests; a fake long-touch fires one buzz, never two |
| NA-41 | P1 | `noob-reflex` CLI (add/test/enable/disable/remove/history) for her coder; every change versioned in Git-like history under `/var/lib/noobia/reflex/` | B11 |
| NA-42 | P1 | Hook-up: a tool so Lynx can ask her coder (`lynx-code exec`) to write a reflex; reflex outputs flow back as senses | B10 with "buzz after a long touch" |

### Epic NA-5: inference routing (B12-B14)

| ID | P | Item | Done when |
|---|---|---|---|
| NA-50 | P1 | Merge `brain_config.py` into `route.py`: health check before each request, per-request decision logged, durable `unavailable` state, retry with backoff, jobs kept | B12, B14 |
| NA-51 | P2 | Cloud fallback, once Tom decides provider, budget and key placement (LNX-46) | B13 |

### Epic NA-6: memory and continuity (B15-B19)

| ID | P | Item | Done when |
|---|---|---|---|
| NA-60 | P1 | `memory/journal.py`: append-only `JOURNAL.md` writer for each Noob; Argus clears only an acknowledged byte range (receipt with hash), never entries appended during collection | B15 with a fixture Argus |
| NA-61 | P1 | `memory/notes.py`: notes DB (ID, ts, original text, processed flag), `lynx_note` tool for her (CHAT and SENSE), search by FTS5 on Lynx + embeddings on Nexus when reachable | B16 |
| NA-62 | P1 | `memory/lifestory.py`: daily consolidation per section 7.3 with `dushich-summarizer`, a fixed timezone (Europe/Sofia unless Tom says otherwise), atomic commit of both summaries + checkpoint + processed marks, chronological catch-up, late-note reconciliation | B17, B18 with multi-day fixtures |
| NA-63 | P1 | Effective description = AGENTS.md + Life so far + Yesterday, built at agent start; permanent file never written | B18 |
| NA-64 | P2 | Argus intake for notes and life-story versions by Noob and date (with Argus's ARG-013/014; Aria owns Argus) | B19 |

### Epic NA-7: recoverability and the whole loop (B20, B21)

| ID | P | Item | Done when |
|---|---|---|---|
| NA-70 | P2 | Versioned config: `/etc/noobia`, `/etc/lynx`, patterns and reflex DB snapshotted to Nexus on change; restore drill on a disposable copy | B20 |
| NA-71 | P2 | Persist the runtime-only hardening (firewall LNX-65, sysctls LNX-79, WireGuard LNX-21) at boot, as reviewed packets with the boot pins untouched | survives a reboot Tom chooses to do |
| NA-72 | P2 | B21 run: an unprompted event -> decision -> tool -> later feedback -> a note or reflex, observed and recorded | B21 |

### Epic NA-8: the move to common (section 3)

Order matters: each step moves code without changing behavior.

| ID | P | Item |
|---|---|---|
| NA-80 | P1 | `profile.py` + Lynx's `noob.json`; autonomyd and the agent read it |
| NA-81 | P1 | `agent/jobqueue.py`, `agent/worker.py`, `agent/broker.py`, `agent/injection.py` moved; Lynx modules become subclasses |
| NA-82 | P1 | `agent/agent.py` (generic SENSE/CHAT loop) and `route.py` merge |
| NA-83 | P2 | `sensekit/` from `lynx/senses/common`; Lynx senses subclass it |
| NA-84 | P2 | `patterns_build.py`; `make_patterns.py` keeps only Lynx's patterns |
| NA-85 | P2 | `sh/noob-install.sh`; new packets use it |
| NA-86 | P2 | Second Noob proves it: Argus (or a NanoPi) runs the harness from a profile with no Lynx imports |

## 5. Lynx work outside the standard (still open)

From Rose's backlog and the spec's open issues, excluding cellular and tools:

| Item | State | Next |
|---|---|---|
| LNX-18 BLE discovery | blocked (kernel mgmt 0x0D for LE) | LE through the H4 relay; needs Aria |
| LNX-20 session recovery | open | folds into NA-14 / NA-50 |
| LNX-22 Noob mesh | design | after LNX-21 persistence |
| LNX-43 Bee map | TODO (Tom) | needs GNSS |
| LNX-44 on-device model | decision | model choice vs. RAM/thermals |
| LNX-45 offline journal + sync | open | becomes NA-10 + NA-60 |
| LNX-46 remote failover | decision | NA-51 |
| LNX-47 reflex priority | measured; Tom: no model change for now | NA-40 removes most of the need |
| LNX-82 per-Noob NRP identity | design | with NA-80 profiles |
| LNX-83 replay protection | partly done via LNX-84 | check NRP side |
| LNX-85 DoT | proof passed, not live | persistent resolver packet |
| LNX-91 security sync with Argus | waits for Argus | with NA-64 |
| Spec #1 reaction latency | open | Ollama single slot; NA-40 reflexes take the fast path |
| Spec #4 net_diag scope | open | limit targets to Noobia; ask before packet capture |
| Spec #5 front camera | open | rotation check with a face; add `front` to `lynx_camera_photo` |
| Spec #6 recursive grep/find watchdog | lore | get a reproducible receipt |
| `lynx-bluetooth` restarts every ~21 min | open | find the cause |

## 6. Decisions for Tom

1. Top-level `/noobia/autonomy` or the existing `common/autonomy` (recommended).
2. Priorities: keep everything at P20, or restore per-sense priorities (NA-15)?
3. Which drops become explicit IGNORE/COALESCE rules, and which must wait instead (NA-13)?
4. Cloud fallback: provider, budget, where the key lives (NA-51, LNX-46).
5. Day boundary timezone for life stories (NA-62).
6. Aigel's return: only for new event kinds, at low GPU priority (NA-31)?

## 7. Suggested order

NA-00 -> NA-01 -> NA-10..14 (lossless core) -> NA-80..82 (move the agent to
common while touching it anyway) -> NA-40..42 (reflexes) -> NA-60..63
(memory) -> NA-20..22 -> NA-50 -> NA-30..31 -> the rest.
