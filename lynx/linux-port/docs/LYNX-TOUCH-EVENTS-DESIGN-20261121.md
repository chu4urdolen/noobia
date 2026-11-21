# Lynx touch events for agents: consumption analysis and design (2026-11-21)

Gwyn queue item 2 (forge #113). This is offline analysis only: nothing is
deployed, no phone contact. Aria decides on any runtime change.

## Facts (source-cited, pinned by `lynx/tools/ui/test_touch_queue_contract.py`)

- **One reader of the panel.** `lynx-noobd` opens `/dev/input/event0`
  (`lynx_noob_runtime.py:41`, `TouchInput` at `:216`) without `EVIOCGRAB`.
  It turns touches into records in one `RecordQueue`.
- **Small ring.** The queue holds 8 records. On overflow the oldest is
  dropped and `dropped` is counted (`:188-209`).
- **`TOUCH_STATUS` (380) does not consume.** It returns `panel`, `down`,
  `queued` and `dropped` (`:991-995`).
- **`TOUCH_POLL` (381) consumes.** It pops the oldest record (`:997-999`) and
  is the only code that pops the queue. The queue is shared by **every** NRP
  caller. No in-tree program or tool polls it today.
- **Lynx's own screen UI is not affected.** It does not read this queue.

So a draining agent tool would take events away from any other NRP client
(a VM program, a Nexus script) polling at the same time. Today it would
compete with no one. That could change silently.

## Proposal

1. **Ship now: a peek tool, read-only and non-consuming.** Add
   `lynx_touch_events` with no inputs, running `TOUCH_STATUS`.
   - It reports `down`, `queued`, `dropped` and the panel state.
   - Effect: `read_only`. Status companion: itself. No stop needed.
   - This alone can show a person's touch arriving: `queued` or `down`
     changes while someone touches the screen.
2. **Optional: a capped drain.** `lynx_touch_drain {"max": 1..8}`, effect
   `read_only` but labelled **"consumes queued touch events"**.
   - It calls `TOUCH_POLL` up to `max` times with `empty_ok` and returns the
     records.
   - Add it only after Aria confirms that no other NRP client relies on the
     queue.
3. **Better long term (runtime change, Aria's decision):** a `TOUCH_PEEK`
   native that returns a copy of the queued records without popping, or a
   per-client cursor. Agents could then see touches without taking them from
   anyone.

**Physical proof still missing for all three:** an attended receipt of a
person's touch arriving through the agent call. That trial would be Aria's,
with Noob touching the screen.

## Proposed manifest (not installed; `local_calls` unchanged)

```json
{"name": "lynx_touch_events",
 "description": "Entity: Lynx. Read touch queue state (finger down, queued, dropped) without consuming events.",
 "inputSchema": {"type": "object", "properties": {}, "required": [], "additionalProperties": false},
 "timeout": 5}
```

Its wrapper would call `TOUCH_STATUS` through the existing runtime. Adding
it changes the 38-tool catalog, so it follows the normal Aria review and
install path. The coverage audit then classifies it under `platform/touch`
as `read_only`.
