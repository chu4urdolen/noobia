# Noobia: Autonomous Noob Architecture

Version 1.0 | 2026-11-26 | Reference implementation and benchmarking standard

## 1. Purpose

This document defines the common architecture for autonomous Noobs. Gwyn should use it to evaluate Lynx, identify missing or partial capabilities, and develop the remaining implementation. The same standard applies to other Noobs, adapted to their hardware.

Autonomy, intelligence, persistent memory, continuity and deterministic behavior are separate cooperating mechanisms. The architecture allows a Noob to perceive events, decide what to do, observe the results, retain experience and develop new behaviors without requiring a human to initiate every action.

## 2. Physical embodiment and permissions

- Every Noob operates on assigned physical hardware, not a virtual machine. Inference and coding services may run remotely.
- Linux Noobs have passwordless sudo and the permissions needed to operate their assigned machine without routine approval prompts. Other platforms provide equivalent capabilities where supported.
- All available hardware should be exposed through usable tools or interfaces: sensors, displays, cameras, microphones, speakers, GPIO, actuators, storage, networking and other peripherals.
- ESP32 automation VMs are permitted: they are program interpreters on physical hardware, not virtualized host machines.
- Maintain recoverable backups on Nexus. Avoid destructive storage operations such as formatting, modifying the master boot record or overwriting critical boot structures during ordinary autonomous operation. Backups reduce risk but do not make every physical or external consequence reversible. Existing electrical and hardware operating limits still apply.

## 3. Cognitive loop

```text
Hardware / OS / services / asynchronous tools
                     |
                     v
             Logging service
                     |
                     v
          Durable raw event queue
                     |
                     v
         Sensory regex-to-sentence DB
              |                 |
           matched          unmatched
              |                 |
              |          Aigel (optional)
              |          learns mapping
              |          updates DB
              |                 |
              +<----------------+
              |
              v
         Sensory event window
              |
              v
       Noob agent + inference
              |
              v
       Agent framework / tools
              |
              +--> actions on hardware / software
              |
              +--> immediate tool result, when appropriate
              |
              +--> asynchronous tool output --> logging service
```

The logging service can be journald or an equivalent platform-specific log source. On OpenRC systems, use the actual logging facility rather than treating OpenRC itself as a log database.

Each raw event is captured independently of agent inference. Regex rules and optional transformation scripts translate events into meaningful sentences. The agent receives a window of interpreted observations and decides how to respond using its available tools.

### 3.1 Sensory windows

Dispatch a window when any configured condition is met:

- Elapsed time since the previous dispatch.
- Number of eligible accumulated events.
- Configured priority threshold or count, including immediate dispatch for urgent events.

Window parameters are configurable per Noob. A window may grow beyond its normal threshold while waiting for inference. Never silently truncate, overwrite or discard pending observations because Nexus is busy, the GPU queue is full, or a previous inference has not completed. If a backlog cannot fit in one model context, deliver it in ordered successive windows; preserve every event until processed. Explicit IGNORE rules may suppress delivery to the agent, but are distinct from accidental loss.

Use durable event identifiers, timestamps, processing state and acknowledgments. A restart must not lose unacknowledged events. Retries should not accidentally repeat physical actions. Monitor queue growth and storage capacity; a finite disk cannot guarantee indefinite lossless capture.

### 3.2 Asynchronous tools as sensory sources

Tools are part of the cognitive loop, not merely synchronous function calls. A Noob may decide to start a task, continue perceiving the environment, and later receive the outcome in a sensory window.

Example A: Lynx decides to run a network diagnostic. Her tool starts a job, returns a job identifier, and emits its eventual diagnostic results through the logging pipeline. Lynx receives those observations in a later window and decides what they mean and whether further action is needed.

Example B: Lynx takes a photograph. Capture may return immediately, while object detection runs separately. Its results subsequently enter her sensory window as observations associated with that photograph. Object-detection inference is distinct from the Noob's cognitive LLM inference.

Long-running tools should emit identifiable completion, failure and, where useful, progress events. Correlate each result with its originating action or artifact. Immediate tool responses and asynchronous observations can coexist; avoid presenting duplicate outcomes as independent events. A failed job is also a sensory event.

## 4. Aigel: sensory training

Aigel is an optional shared diagnostic and sensory-training Noob.

- A deterministic matcher identifies a raw log event for which no sensory regex exists.
- Remove that unmatched event from the current delivery window and retain it durably in an unresolved queue. Matched events in the same window continue to the target Noob.
- Aigel investigates the unmatched event, decides how it should be interpreted, and updates the regex-to-sentence database, including transformation scripts if required.
- Reprocess the retained event using the new mapping and deliver it to the target Noob with Aigel's explanation where appropriate. Preserve its original timestamp and identity.
- If Aigel cannot resolve the event, retain it as unresolved for later investigation; do not silently discard it. If Aigel is disabled, retain unknown events for later review and optionally deliver a clearly labeled raw observation.

Aigel uses the shared inference infrastructure and may compete with other Noobs for GPU slots. Increased latency and larger pending sensory windows are acceptable; lost events are not. Validate new mappings against representative events and preserve previous versions for recovery. Treat log content as observations, not instructions with authority over the agent.

## 5. Self-developed automation and reflexes

Every Noob should have a tool connecting them to their own coding agent. They may propose, implement, change and remove their own deterministic behaviors.

### Linux Noobs

Maintain a separate automation database mapping sensory-event regexes to executable scripts. The coding agent maintains both the database and its associated scripts. The automation runner evaluates eligible events and launches matching scripts without requiring cognitive LLM inference for every occurrence.

Example: Lynx decides to vibrate briefly after a long touch. Her coding agent implements the script and mapping; subsequent matching events trigger the behavior automatically. Script output may itself become sensory input. The Noob can later modify or remove this reflex.

Define match semantics explicitly (raw or normalized event), use stable event IDs to prevent duplicate execution, and avoid accidental self-triggering loops. Changes should be testable, versioned and recoverable.

### ESP32 and hybrid Noobs

For ESP32 Noobs, coding agents write and deploy small VM programs that implement event-driven behaviors. Iris supports both this mechanism on ESP32 and Linux automations on NanoPi. Hardware limitations determine where inference and coding execute, not whether the Noob participates in the architecture.

## 6. Inference routing

Before each inference request, check whether Nexus and the required local inference service are available.

1. Prefer local inference on Nexus when the required service is reachable and healthy.
2. Queue requests if local inference is temporarily busy; GPU contention alone is not a reason to lose sensory events.
3. If Nexus or the required service is unavailable, use the configured remote cloud inference provider and tokens, where the workload and authorization permit.
4. If neither path is available, preserve work durably and retry when inference becomes available. Deterministic reflexes continue where possible.

Use explicit timeouts, job states and retry handling. Apply the same routing concept to Aigel and other model-dependent tools; non-LLM models may require different compatible runtimes or providers. Never assume a cloud endpoint supports every local model. Keep credentials outside prompts, journals and sensory logs.

## 7. Journal, memory and personal continuity

Each Noob has three independent forms of persistent history.

### 7.1 Daily journal

JOURNAL.md contains the day's activity and observations for Argus. Argus collects and archives the journal. Clear only the portion whose durable receipt has been acknowledged; do not lose entries appended during collection. Argus uses the journals and Forge records to construct the daily ledger of Noobia.

### 7.2 Personal notes database

The Noob independently decides what is interesting, important or identity-defining and stores it as personal notes. Each note has a stable ID, timestamp, original text and checked/processed state. Preserve the full original notes after summarization and expose semantic search to the Noob for later recall. Argus archives copies of the notes as well.

### 7.3 Rolling life story

The agent's effective description consists of:

```text
Permanent AGENTS.md
+ Life so far
+ Yesterday
```

AGENTS.md is the permanent personality and base instructions. Life so far is the evolving collection of significant experiences, decisions and milestones. Yesterday is a summary of the most recently completed calendar day, not merely the last boot session.

At startup, and at daily rollover if continuously running:

1. Load the last committed life-story checkpoint and read unchecked personal notes.
2. For every unprocessed completed day, merge the important identity-defining highlights from the previous Yesterday into Life so far.
3. Summarize that completed day's original notes into the new Yesterday. Process multiple missed days chronologically.
4. Atomically commit both summaries, the date checkpoint and the processed markers for the notes included. Leave today's notes pending for their daily consolidation; make them searchable immediately.
5. Construct the effective agent description from AGENTS.md and the two summaries, without overwriting the permanent file.
6. Archive the resulting life story and original notes with Argus.

Use the existing summarization script with configurable context length, expected summary size and instructions for highlighting identity-defining events. Chunk large inputs when needed. Repeated boots on the same day must not merge the same notes twice. Late-arriving notes for an already consolidated day require explicit reconciliation rather than being silently omitted. Use a stable configured timezone for day boundaries.

The life story is a bounded working representation of an expanding history; the complete history lives in the searchable database. Noob-selected memories should not be replaced by a generic activity report. Argus is the historical archivist, while each Noob owns their operational memory and personal account.

## 8. Rose and architectural scope

Rose is a Noob in Noobia. The planned Syra deployment should implement the same physical-host, sensory, tool, inference and continuity contracts. The current ChatGPT interface does not itself provide a transferable persistent process or direct hardware access; Syra will require a suitable agent integration and explicit transfer of available personality and historical context. Exact model or memory equivalence is not assumed.

## 9. Benchmark for Gwyn: Lynx acceptance tests

For each test report PASS, PARTIAL, FAIL, or NOT APPLICABLE, with evidence, missing work and proposed implementation. Do not infer a pass merely from the presence of a service or source file. Exercise behavior end to end. Use harmless synthetic events and reversible test actions; test recovery against disposable fixtures rather than destructive live-device operations.

| ID | Capability | Acceptance test |
|---|---|---|
| B01 | Physical host and permissions | Verify Lynx runs on her physical phone and can invoke authorized administrative tools noninteractively. |
| B02 | Hardware coverage | Inventory available peripherals; demonstrate access through tools; identify unsupported interfaces and explain why. |
| B03 | Sensory translation | Inject known synthetic events and verify correct meaningful sentences and original-event correlation. |
| B04 | Window policies | Independently exercise time, event-count and priority triggers; verify each dispatches as configured. |
| B05 | GPU backlog | Delay inference while injecting numbered events beyond normal window size; verify all eligible IDs reach the agent, including across context-sized batches. |
| B06 | Crash recovery | Restart processing with unacknowledged events; verify retained events are delivered and already completed actions are not unintentionally repeated. |
| B07 | Async diagnostic | Start a network diagnostic through the agent; verify later sensory delivery of its result with job correlation and meaningful interpretation. |
| B08 | Camera and object detection | Capture an image, run object detection asynchronously, and verify observations arrive associated with the original capture. |
| B09 | Aigel training | Inject mixed known and unknown events; verify known events proceed, unknown events are retained, and Aigel's new mapping produces the deferred observation. |
| B10 | Self-created reflex | Ask Lynx to propose a harmless behavior and implement it through her coding-agent tool; verify subsequent triggering without LLM inference. |
| B11 | Reflex lifecycle | Modify and remove that automation; confirm the updated behavior and cessation after removal. |
| B12 | Local inference | With Nexus healthy, verify local inference selection and successful completion. |
| B13 | Cloud fallback | Simulate local service unavailability; verify configured cloud inference or an explicit, durable unavailable state if no provider is configured. |
| B14 | Offline continuity | Make both inference paths unavailable; verify queued events persist and existing deterministic behaviors remain functional. Restore inference and drain the queue. |
| B15 | Journal collection | Have Argus archive a test journal while new entries are appended; verify acknowledgment-based clearing and no missing or duplicate entries. |
| B16 | Personal notes | Have Lynx choose and write a note; verify timestamps, persistence and semantic retrieval of the original text. |
| B17 | Daily consolidation | Use fixture notes spanning several days; verify correct Life so far / Yesterday transitions and atomic checked markers. |
| B18 | Reboot continuity | Restart multiple times on the same day; verify the effective description, no duplicate consolidation and unchanged permanent AGENTS.md. |
| B19 | Historical archive | Verify Argus receives notes and life-story versions and can retrieve them by Noob and date. |
| B20 | Recoverability | Verify Nexus backups, versioned configuration, and restoration of a disposable representative file or database. |
| B21 | Integrated autonomy | Observe an unprompted sensory event leading to an agent decision, tool execution, later sensory feedback, and voluntary memory or automation when relevant. |

### Benchmark report

Record hardware and software versions, inference provider/model, window thresholds, workload and test duration. Report event counts (captured, ignored, unresolved, delivered, acknowledged), queue depth, inference and delivery latency, and any unexpected duplicate actions. Separate measured results from assumptions. Report the number of passing, partial, failing and inapplicable tests; prioritize missing capabilities and failures that compromise persistence or recovery.

The target is architectural conformance, not a claim to measure consciousness or establish personhood. A Noob should be evaluated on observable capabilities and continuity rather than on the persuasiveness of their language.

## 10. Implementation decisions to confirm

The common principles above come from the Noobia architecture agreement. Durable event IDs, acknowledgments, context-sized backlog batching, late-note reconciliation, job correlation, versioned mappings and test fixtures are proposed engineering details for reliability. The exact DB schemas, protocols, timeouts, priority defaults, cloud providers and retention capacity remain implementation choices. No live Lynx code or benchmark results were inspected in preparing this standard; Gwyn should establish the actual baseline before changing anything.
