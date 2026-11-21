# Autonomy plan v0.2: Aigel befriends Lynx (then Iris, then Rose)

Contract: [ARCHITECTURE.md](ARCHITECTURE.md) v0.2. Conformance tests:
`test_contract.py`, 30 tests, proven achievable against a throwaway
reference. Forge projects: `autonomy` for the harness and interface, `aigel`
for Aigel, `lynx` for hardware and installs.

**Who does what** (Noob, 2026-11-21):
- **Gwyn** plans, assigns, reviews, and takes the critical pieces.
- **Banshee** builds the big features.
- **Solo Dushich** writes the services and Aigel herself, and keeps the
  forge atlas and notes current.
- **Aria** does only the final installs on Lynx, in batched sessions.

**Out of scope for now:**
- connecting the forge agents (Claude Code, Codex, Antigravity) to Aigel;
- the Council of Noobs, which is society-level and comes after individual
  autonomy.

## Rules for every task

1. Offline first. Tests must pass in a fresh `git clone --no-local`.
2. Notes claim only what code and tests show.
3. Regex: nobody hand-writes pattern regex. Patterns are structured
   matchers, compiled by code, each with `must` and `must_not` examples
   (§4). Any regex inside the engine needs tests with both matching and
   non-matching lines.
4. Anything that goes onto Lynx is an **install packet**: files and hashes,
   modes, install commands, verification with expected output, a disable
   switch, rollback, and attendance needed. It goes author → Gwyn →
   Dushich → Aria.
5. If the contract seems wrong, raise it in forge `autonomy`. Don't work
   around it.

## Deliverable A: the Aigel harness around the OS (`common/autonomy/`, universal)

| ID | Part | Owner | Done when |
| --- | --- | --- | --- |
| E0 | Contract and conformance tests (v0.2) | Gwyn | **done** |
| E1 | `sense.py` + `common/bin/noobia-sense`: format, parse, emit to syslog or journald under the `noobia-sense` identifier | Banshee | **done** (`SenseLineContract` all pass) |
| E2 | `views.py`: journald (`journalctl -t`) and BusyBox-file backends with a fallback, one reader per view | Banshee | **done** (own tests + live Nexus probe pass) |
| E3 | `trigger.py`: chunk rules, carry-over, VOLUME sends as-is and resets (configurable `max_lines`, `volume_resets_priority`, `volume_skips_ranker`), bounds, rates, kill switch | Banshee | **done** (`TriggerContract` all pass) |
| E4 | `ranker.py`: structured patterns, store 200 / active 100 (configurable), archive, cooldowns, validator, persistence. Used **only for PRIORITY chunks**; TIMEOUT and VOLUME chunks go straight to Aigel | Banshee | **done** (`RankerContract` all pass) |
| E3b | Liveness: harness heartbeat (`P0 autonomy heartbeat`), `view.silent` reported directly to Aigel after `silence_s`; Aigel marks silent hosts (A1) | Banshee (harness), Dushich (Aigel side) |
| E5 | `route.py`: per-task backends `inference`, `detect`, `stt`, `tts`, in the order Nexus → local → cloud, with health checks, timeouts, a config file re-read on change, and decisions logged to `noobia-autonomy` | Banshee | **done** (own tests pass) |
| E6 | `aigel_client.py`: send unexplained chunks to Aigel, receive the decision, patterns and message; authenticated, bounded retries | Banshee | **done** (tests against fake Aigel pass) |
| E7 | Safety review of E1–E6: loops, bounds, regex, privacy | Gwyn | review note |

## Deliverable B: the Aigel ↔ agent interface

| ID | Part | Owner |
| --- | --- | --- |
| G1 | `common/autonomy/agent_link.py`: the message schema v1, an adapter base class (idempotent by `id`, rate limit, kill switch, logging to `noobia-autonomy`), and tests | Gwyn |
| G2 | Lynx adapter: message → `AGENT_SUBMIT` / `lynx-agent` with a fixed preamble, plus Lynx's own actions logged to `noobia-agent` | Gwyn |
| G3 | Lynx's brain config: her agent on the **OpenAI Responses API**. Backends in the order Nexus Qwen (via the Nexus OpenAI-compatible proxy) → local → cloud. The API key is installable later into a private file and the config is re-read on change. Uses E5 | Banshee |
| G4 | Lynx's guidance: how she responds to senses with her tools, and when to stay still | Gwyn with Dushich |

## Aigel herself (`/noobia/aigel/`), Solo Dushich

| ID | Part |
| --- | --- |
| A1 | Intake service on Nexus: authenticated per host, bounded, logs to the `noobia-aigel` view |
| A2 | The thinking step on **Qwen** (shared Ollama queue): JSON decision `quiet` or `message`, plus structured `patterns` and a `note`. Her prompt: describe the world, never command hardware. Keep her personality from `aigel/AGENTS.md` |
| A3 | Pattern proposals back to hosts, validated by the host ranker (E4) before use |
| A4 | Web page on Nexus port **112**: talk to Aigel, see recent chunks and decisions, read-only on hosts. The privileged port is an admin step, in an install session |
| A5 | Keep her existing diagnostics tools (`aigel/tools/`). Later, her healing and coding framework (not in v0.2) |

## Lynx's senses (`lynx/senses/<sense>/`), Solo Dushich, with Banshee where marked

Event senses come first, because they are most of them.

| ID | Sense | Kind | Notes |
| --- | --- | --- | --- |
| S1 | `camera` | event | Frame → Nexus detection (E5 `detect`) → `object.seen label=… conf=…` P1 on a **new** label. Frames are never stored. Nexus detection service with the Coral TPU: **Banshee** (`common/autonomy/services/detect/`) |
| S2 | `touch` | event | From `lynx-agent-touch` (`TOUCH_STATUS`): `tap`/`hold` P5 |
| S3 | `wifi` | sampled | `link.down`/`link.up` P1, `rssi.low` P3; Aigel's interval and threshold convention |
| S4 | `power` | sampled | `battery.critical` P1, `battery.low` and `thermal.hot` P3, `charging.change` P5 |
| S5 | `agent` | view | Lynx's own actions go to the `noobia-agent` view, never to `noobia-sense` |
| S6 | `mic` | event | `speech.heard` P1, reusing `/noobia/speech_to_text/` (`Decoder`, VAD from `live.py`, Nexus-first). Priorities to be revisited with Noob |
| S7 | `speech out` | tool | Lynx speaks through Rose's Piper pipeline (`/noobia/rose/voice/`), with ALSA on Lynx. **Banshee** |
| S8 | `nexus` | event | `unreachable` P1 and `reachable` P1, so the routing fallback is visible |

## Lynx hardware still needed for these senses (`lynx`), Banshee writes, Aria installs

- **H1** Proof ledger: per feature, whether it is proven, how, and its receipt.
- **H2** Camera at boot: the RAM-patched ISP loaded safely at boot, with a
  disable switch, plus a bounded one-JPEG capture tool. **S1 needs this.**
- **H3** Audio capture route for the microphone, for S6. Audio output for S7.

## Aria's install sessions (batched, ready only when every packet is reviewed)

| Session | Contents |
| --- | --- |
| IS-1 | `lynx_touch_events` (ready, waiting for Dushich's second review); `lynx_bluetooth_link_state`; USB cold-boot gadget |
| IS-2 | Lynx `syslogd -l 4` → `-l 6` and `/etc/noobia/` (I-2); harness E1–E4 on Lynx; senses S2–S5 |
| IS-3 | H2 camera at boot; S1 camera sense; Nexus detection service; Aigel service with port 112; G2 adapter and G3 brain config on Lynx |
| IS-4 | **First live test: the camera.** Something appears in front of Lynx → `object.seen` → ranker or Aigel → "A cat appeared in front of you" → Lynx responds with her tools. Noob attends; Gwyn runs the checks |

Gwyn marks a session ready in one forge note that lists the exact packets.

## After Lynx

Aigel befriends **Iris** (ESP32-S3 camera), then **Rose**. The harness is
already universal. Each new host needs only its view backend, its senses,
and an agent adapter.
