# Noobia Autonomy: Aigel, the senses, and a living Noob

Status: **design contract v0.2**. Gwyn wrote it on 2026-11-21 from Noob's
description and clarifications. Everyone builds against this file. Change
it only with a forge note (project `autonomy`) and a commit, never silently.

## 0. What this is and is not

**Is.** Individual autonomy for a Noob that lives on her own machine. The
machine's senses report what happens. **Aigel** reads what cannot be
explained cheaply and tells the Noob what matters. The Noob decides what to
do, through her own tools.

The order is: **Aigel befriends Lynx first, then Iris, then Rose.**

**Is not (yet).**
- The forge agents (Claude Code, Codex, Antigravity) are not wired into
  this.
- The society-level **Council of Noobs**, where Noobs meet and agree on new
  code, comes later and is a different design.

**Aigel.**
- She is Noobia's little AI angel. Her name sounds like "noble", like a Nob.
- She is the **nurse angel** between a machine's senses and its Noob.
- She runs on Nexus on **Qwen**, like the other local minds, through the
  same Ollama queue.
- Later she gets a coding framework so she can heal Noobs herself. That is
  not part of v0.2.
- Her files live in `/noobia/aigel/`.

**Two deliverables, both universal:**
- **A. The Aigel harness around the OS** (`common/autonomy/`):
  - the sense emitter;
  - log views;
  - the trigger and chunker;
  - the pattern ranker;
  - the compute router;
  - the client that talks to Aigel.

  Every host that carries a Noob runs it.
- **B. The Aigel ↔ agent interface** (`common/autonomy/agent_link.py`): one
  message schema and one adapter base class. Each Noob implements a small
  adapter. Lynx's adapter feeds her agent, which thinks through the
  **OpenAI Responses API**.

```
 senses (services)        THE HOST (Lynx)                                   NEXUS
 ────────────────         ──────────────────────────────────────────        ─────────────
 wifi, power, camera ─▶  [view: noobia-sense] ─▶ trigger/chunker ─▶ ranker ─┬─ explained ─▶ agent_link ─▶ Lynx's agent
 touch, mic, ...                                    │ carry-over            └─ unexplained ─▶ Aigel (Qwen) ─▶ agent_link
                                                    ▼                                         │  ▲
                        [view: noobia-autonomy]  decisions log                 patterns back ◀┘  └─ web :112 (people)
                        [view: noobia-agent]     Lynx's own actions (never read by the trigger)
                        [view: noobia-aigel]     Aigel's messages   (never read by the trigger)
 Lynx's outputs: screen, flashlight, haptics, speaker (and later voice)   Lynx's own web page (people)
```

## 1. Sense lines

Each sense writes one syslog line per observation, under the identifier
`noobia-sense`:

```
NOOBIA P<n> <sense> <event> [key=value ...] | <free text for people and Aigel>
```

- **Priority `Pn`, n from 0 to 99.** `Pn` with n ≥ 1 means: trigger once
  the current chunk holds **n** lines of `Pn`. So `P1` triggers on the
  first line and `P15` on the fifteenth. `P0` is plain activity and never
  triggers by priority.
- `<sense>` is `[a-z0-9_]{1,24}` and `<event>` is `[a-z0-9_.]{1,48}`.
- There are at most 8 `key=value` pairs. Keys are `[a-z0-9_]{1,24}`;
  values are ASCII without spaces, quotes or `|`.
- The whole line is at most 512 bytes. The emitter truncates on a UTF-8
  character boundary, never the reader.
- `cause=self` marks a line caused by the Noob's own action. It is the
  second guard against loops; views are the first (§3).
- Everyone emits through `common/autonomy/sense.py` (`format_line`,
  `emit`) or the `noobia-sense` command. Nobody formats lines by hand.

### Two kinds of senses

- **Event senses (most of them)** emit one line when something happens:
  `camera object.seen` ("I see a cat"), `sms received` ("I got an SMS
  saying 'You're a Noob'"), `mic speech.heard`, `touch tap`,
  `wifi link.down`. No polling interval is involved.
- **Sampled senses (a few)** watch a value over time, such as battery,
  thermal or Wi-Fi signal. They follow Aigel's existing granularity
  convention: `sample_interval_ms` and `sample_period_s` in config, plus
  per-metric `warn`/`fail` thresholds. They emit a priority line only when
  a threshold is crossed or the state changes, and otherwise at most `P0`
  summaries at their period. They never emit every raw sample.

### Default priorities

Gwyn set these defaults; they will be revisited when speech arrives. They
follow the existing Aigel convention that each threshold has a `warn` and a
`fail` level (`aigel/config.json`, `aigel/tools/aigel_sentinel.py`).

| Severity | Default priority | Examples |
| --- | --- | --- |
| fail, or something a person would want to know now | `P1` | `wifi link.down`, `power battery.critical`, `camera object.seen` (a new label), `mic speech.heard` |
| warn | `P3` | `thermal hot`, `wifi rssi.low`, `power battery.low` |
| routine change | `P5` | `touch tap`, `power charging.change` |
| status sample | `P0` | `battery level`, `wifi rssi` |

Each sense keeps its own map in its config, so a host can retune it.

## 2. The trigger and the chunk rule (exact)

The trigger reads **only** the `noobia-sense` view (§3) and builds one open
chunk at a time.

**A chunk closes for one of three reasons:**

1. **PRIORITY:** for some n ≥ 1, the chunk holds n lines of `Pn`, counting
   lines carried over from earlier chunks.
2. **VOLUME:** more than `max_lines` (default **15**) lines have **arrived
   during this chunk**. Carried lines don't count here.
3. **TIMEOUT:** `window_s` (default **60** s) has passed since the chunk
   opened, and it holds at least one line.

`cause=self` lines count toward **no** rule. They stay in the chunk as
context, and they do count toward the size limits.

**What is sent, and what is carried:**

- **On PRIORITY:** the whole chunk goes on, carried lines included, in
  order. Nothing is carried.
- **On TIMEOUT:**
  - Every `Pn` line with n ≥ 1, carried or new, is **removed** and
    **carried, in order, to the front of the next chunk**, where it keeps
    counting toward its threshold.
  - The rest (`P0` and `cause=self` lines) goes on.
  - If nothing is left after the removal, nothing is sent.
- **On VOLUME** (Noob, 2026-11-21): the chunk is sent **as it is**, with
  carried and priority lines included and nothing stripped, and the
  **priority counters reset** (nothing is carried). It goes **straight to
  Aigel's LLM**, skipping the regex ranker. All three are configurable while
  we think this through:
  - `max_lines` (default 15);
  - `volume_resets_priority` (default `true`; `false` strips and carries
    priority lines the way TIMEOUT does);
  - `volume_skips_ranker` (default `true`).

Example (Noob's, and pinned by a test): 10 `P15` lines arrive within 60 s,
and the chunk closes on TIMEOUT. Its `P0` lines go to the ranker, and the
10 `P15` lines start the next chunk. Five more `P15` lines arrive within the
next 5 s. That makes 15, so the chunk closes on PRIORITY and all 15 lines
go on together, in order.

**Carry bounds** (Gwyn's proposal, so nothing waits forever):
- at most `carry_max_lines` (default 200) lines;
- a carried line older than `carry_max_age_s` (default 600 s) is released
  into the next chunk that is sent, whatever closed it, marked
  `carried_expired`.

**Rates:**
- at most `max_chunk_lines` (200) and 32 KiB per chunk;
- at most 1 chunk per second, and `max_chunks_per_hour` (30) to Aigel;
- overflow is counted and logged in the autonomy view, never queued without
  limit.

**Where each chunk goes** (Noob, 2026-11-21):

| Close reason | Goes to |
| --- | --- |
| PRIORITY | the **regex ranker** (§4). Its unexplained lines go to Aigel |
| TIMEOUT | **straight to Aigel**, priority lines already stripped and carried |
| VOLUME | **straight to Aigel**, as it is |

The ranker exists only for PRIORITY chunks. If a chunk holds too few
priority lines to trigger, Aigel decides what to do with what she sees. We
will tune this by reassigning priorities and reconfiguring the trigger once
we see it running. `volume_skips_ranker` and a matching
`timeout_skips_ranker` (both default `true`) keep this configurable.

**Liveness: silence is a symptom.** On 2026-11-21, Lynx's syslog went
silent for two hours before she rebooted, and nothing noticed. To catch
this:
- Each host harness emits its own heartbeat sense line every
  `heartbeat_s` (default 300 s), `NOOBIA P0 autonomy heartbeat`.
- If the trigger's view backend sees **no line at all** (heartbeat
  included) for `silence_s` (default 900 s), it reports `view.silent`
  directly to Aigel over the client, not through the log.
- Aigel, on Nexus, separately marks a host as `silent` when no chunk or
  heartbeat arrives for `host_silence_s`. That is her first nursing duty.

**Kill switch:** while `/etc/noobia/autonomy.disable` exists, the trigger
sends nothing. The senses keep logging.

## 3. Views: how feedback loops are prevented

A **view** is a set of log identifiers, plus a minimum syslog level.

| View | Who writes | Who reads |
| --- | --- | --- |
| `noobia-sense` | sense services | the trigger, only this view |
| `noobia-autonomy` | trigger, ranker and router decisions (explained, sent, dropped, delivered) | people, Aigel as context on request |
| `noobia-aigel` | Aigel's decisions and messages for this host | people, the Noob's history |
| `noobia-agent` | the Noob's own actions (tool calls, speech out, screen changes) | people, Aigel as context on request |

The trigger never reads anything except `noobia-sense`, so the Noob's own
actions and Aigel's words can never set off a trigger.

**Backends:**
- **journald** (Nexus and other systemd hosts): `journalctl -f -o json -t
  noobia-sense`. Lines also carry the fields `NOOBIA_P`, `NOOBIA_SENSE` and
  `NOOBIA_EVENT`.
- **BusyBox syslogd** (Lynx): tail `/var/log/lynx/messages`, filtered by
  tag. Sense lines are logged at level `notice` (5). BusyBox `-l N` keeps
  only messages **more urgent than N**, so Lynx's current `-l 4` drops
  warnings and notices. Install I-2 raises it to `-l 6`, which keeps notice
  and drops info
  (`lynx/linux-port/docs/LYNX-INSTALL-PACKET-I2-SYSLOG-20261121.md`).
- A fallback like `aigel_dmesg_scout.py`'s `journalctl`/`dmesg` pair.

## 4. Pattern store and ranker (regex done carefully)

Noob's warning: we are bad at regex. So:

- **Patterns are structured matchers, not hand-written regex.**

  ```json
  {"id": "cat-seen", "match": {"sense": "camera", "event": "object.seen",
     "fields": {"label": "cat"}, "text_contains": null},
   "message": "A cat appeared in front of you", "to_noob": true,
   "cooldown_s": 300, "examples": {"must": ["NOOBIA P1 camera object.seen label=cat conf=0.9"],
   "must_not": ["NOOBIA P1 camera object.seen label=dog conf=0.9"]},
   "hits": 0, "last_hit": null, "origin": "human", "added_at": "..."}
  ```

  - Field and text matches are **exact or contains, on literals**. The
    engine compiles them, escaping every literal.
  - An optional `regex` (advanced, rare) is allowed only with at least one
    `must` and one `must_not` example, at most 200 characters, no
    back-references and no nested quantifiers, and it must not match a
    fixed corpus of other senses' lines.
  - Aigel proposes **structured matchers only**.
- Every pattern must match all of its `must` examples and none of its
  `must_not` examples, or it is rejected. This check runs on every load,
  not just once.
- **Two sizes, configurable per host:**
  - `store_capacity`: the full ranked store, default **200**;
  - `active_capacity`: the top patterns used for matching, default **100**.

  Ranking is by recent hits. A pattern pushed out of the store goes to an
  archive file, never silently deleted.
- **Per PRIORITY chunk** (the ranker sees no other chunks):
  1. Each line is matched against the active patterns in rank order.
  2. Matched lines are explained. A `to_noob` pattern delivers its message
     at most once per its own `cooldown_s`.
  3. Unexplained lines go to Aigel. If none are left, there is no LLM call.

## 5. Aigel (on Nexus, Qwen)

She has three channels:
- **In:** unexplained chunks from each host's harness, over authenticated
  HTTP on the Noobia network.
- **People:** a web page on Nexus port **112**. It is privileged, so it
  needs `CAP_NET_BIND_SERVICE` or a socket unit.
- **Out:** messages to a host's Noob via `agent_link`, and structured
  pattern proposals back to that host's ranker.

**Transport:** a host's harness POSTs each chunk to Aigel, and her decision
is the HTTP **reply**. Aigel never opens a connection to a host. The host's
harness then delivers any message locally through its `agent_link` adapter,
and stores any accepted patterns. If Nexus is unreachable, the chunk waits
in a bounded local queue, and the `nexus unreachable` sense makes the
outage visible.

For each chunk she returns JSON:

```json
{"decision": "quiet" | "message", "message": "...", "patterns": [ ... ], "note": "..."}
```

She describes the world; she never commands hardware.

She shares the single-request Qwen queue with Dushich, so the trigger's rate
limits are what keep her load small.

## 6. B: the Aigel ↔ agent interface (`agent_link.py`)

**Message** (one JSON object, at most 2 KiB):

```json
{"v": 1, "id": "<uuid>", "host": "lynx", "time": "<ISO-8601 UTC>",
 "source": "ranker" | "aigel", "kind": "observation" | "alert" | "speech",
 "text": "A cat appeared in front of you",
 "evidence": ["NOOBIA P1 camera object.seen label=cat conf=0.91"],
 "pattern_id": "cat-seen" | null}
```

**Adapter base class:**
- `deliver(message) -> receipt` must be idempotent by `id`, rate-limited,
  and respect the kill switch.
- Each delivery is logged in the `noobia-autonomy` view.
- The Noob's resulting actions are logged in `noobia-agent`.

**Lynx's adapter** (`lynx/tools/agent/lynx_aigel_adapter.py`) puts the
message into her local agent queue (`/var/lib/lynx-agent/jobs`, up to 8000
bytes). The NRP `AGENT_SUBMIT` command is not used, because it accepts only
255 ASCII bytes. The job prompt is a fixed preamble that frames the message
as an observation, not an instruction from a person, followed by the
message as quoted JSON data. The adapter refuses, retryably, when the
worker is stopped or `max_pending` jobs are already waiting.

On hosts without the repository, such as Lynx, the harness is installed in
`/usr/local/lib/noobia/autonomy/`. Her agent decides what to do with her
tools: show an image, light the flashlight, buzz, play a sound, or nothing.

**Lynx's brain** runs through the **OpenAI Responses API** with dynamic
backends (§7):
- first: Nexus, Qwen via the Nexus OpenAI-compatible proxy;
- then: local, if any;
- then: cloud, with an API key **installed later** into a private file that
  is never in Git.

The backend order and endpoints come from a config file that is re-read on
change. Switching needs no reinstall.

## 7. Compute routing: Nexus, then local, then cloud

This is a Noobia-wide design rule. Heavy work goes:
1. **to Nexus** when it is reachable (GPU, and the Google Coral TPU for
   detection);
2. **then on the local machine**, if it can do it;
3. **then to a cloud service**, if one is configured.

`common/autonomy/route.py` gives every task (`inference`, `detect`, `stt`,
`tts`) an ordered, configurable backend list with health checks and
timeouts. The choice is logged in the autonomy view. The existing
speech-to-text system already works this way: Nexus worker first, local
fallback (`/noobia/speech_to_text/transcription_scheduler.py`).

## 8. Senses we will reuse

- **Speech in.** `/noobia/speech_to_text/`:
  - faster-whisper `base`, int8, with VAD;
  - `decode_engine.py` `Decoder.decode()`;
  - VAD and phrase chunking from `live.py`;
  - the JSON-lines socket protocol from `speech_service.py`;
  - about 1.5–2.2 s per 6 s clip.
- **Speech out.** Rose's Piper pipeline in `/noobia/rose/voice/`. Lynx needs
  ALSA output instead of PipeWire.
- **Vision.** Lynx's camera frames go to a detection service on Nexus,
  using the Coral TPU where possible. Only labels and confidences come back
  as sense lines.

## 9. Safety invariants (non-negotiable)

1. **No loops:** views first, `cause=self` second.
2. **Kill switch on every host** (`/etc/noobia/autonomy.disable`). Lynx
   later also gets a physical override (the Alert Slider).
3. **Everything is bounded:** line, chunk, carry, store, rates, message
   sizes, and LLM calls per hour.
4. **Privacy.**
   - Camera frames are never stored by default. They travel only on
     Noobia's network, and only labels become text.
   - Speech becomes text. Raw audio is not kept.
5. **Inspectable:** every decision is a line in a view that people can
   read.
6. **Installs on Lynx are Aria's**, from reviewed install packets.

## 10. First live test

**The camera**, not unplugging the Wi-Fi: cutting the Wi-Fi also cuts
Lynx's route to inference.

1. Something is shown in front of Lynx's camera.
2. Nexus detection produces `camera object.seen label=…`.
3. The ranker explains it, or Aigel learns it.
4. Lynx gets "A cat appeared in front of you" and responds with her tools.

## 11. Where code lives

| Part | Path | Owner |
| --- | --- | --- |
| Harness base: `sense.py`, `views.py`, `trigger.py`, `ranker.py`, `route.py`, `aigel_client.py` | `common/autonomy/` | Banshee |
| Agent interface: `agent_link.py` (schema and adapter base) | `common/autonomy/` | Gwyn |
| Contract tests | `common/autonomy/test_contract.py` | Gwyn |
| Aigel service, web :112, prompts, Qwen calls | `aigel/` (e.g. `aigel/service/`) | Solo Dushich |
| Lynx senses | `lynx/senses/<sense>/` | Solo Dushich |
| Lynx adapter and brain config (Responses API, backends) | `lynx/tools/agent/` | Gwyn (adapter), Banshee (brain config) |
| Nexus detection service (Coral) | `common/autonomy/services/detect/` | Banshee |
| Lynx web page | `lynx/web/` | Banshee |
| Installs on Lynx | install packets | Aria |
