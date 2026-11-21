# Noobia Autonomy: senses → Aigel → a living Noob

Status: **design contract v0.1**. Gwyn wrote it on 2026-11-21 from Noob's
description. Everyone builds against this file. Change it by writing a forge
note and a commit, never silently.

## Purpose

A Noob should respond to the world, not only to a keyboard.
- Her hardware and services report what they notice as **sense lines** in
  the system log.
- A small local **autonomy engine** on her own machine watches those lines.
  It handles the familiar ones with **ranked regular expressions** and wakes
  **Aigel** only for what it cannot explain.
- Aigel is an LLM on Nexus. She reads the leftover chunk, learns new
  patterns, and decides whether the Noob needs to know.
- The Noob gets a short, plain message ("A cat appeared in front of you",
  "The Noobia Wi-Fi is down", "Noob said: Hello Lynx") and acts through her
  own tools.

This is **universal**: every Noob gets the same engine, Lynx first and Gwyn
too. Only the senses and the tools differ.

```
 hardware / services          local machine (every Noob)                Nexus
 ───────────────────          ─────────────────────────────             ─────
 sense services  ──lines──▶  log  ──▶  trigger  ──▶  regex ranker ──┐
 (wifi, camera,               (journald or      (time / volume /     │ unexplained
  touch, mic, ...)             BusyBox syslog)   P1..P9 counts)      │ chunk
                                                        │ explained   ▼
                                                        │       Aigel (LLM) ◀──▶ web :112 (human)
                                                        ▼             │ new regexes, messages
                                   Noob agent  ◀── messages ──────────┘
                                   (Lynx)  ◀──▶ web page (local)
                                      └──▶ tools: screen, light, speaker, haptics
```

## 1. Sense lines (the one format everyone writes)

A sense service writes one syslog line per observation, with syslog tag
`noobia-sense`:

```
NOOBIA P<n> <sense> <event> [key=value ...] | <free text for humans and Aigel>
```

- `P<n>` is the **Noobia priority**, `P1`…`P9`. It is not the syslog level.
  - `P1` triggers immediately.
  - `PN` triggers once `N` lines of that priority are in the current chunk.
  - `P0` means log only: it never triggers by count, but stays in chunks
    for context.
- `<sense>` is lowercase `[a-z0-9_]{1,24}`, for example `wifi`, `camera`,
  `touch`, `mic`, `battery`, `thermal`, `agent`.
- `<event>` is lowercase `[a-z0-9_.]{1,48}`, for example `link.down`,
  `object.seen`, `speech.heard`.
- `key=value` pairs are ASCII, values without spaces or quotes, at most 8
  pairs.
- The text after `|` is free UTF-8 and may be read aloud or by Aigel.
- The whole line is at most 512 bytes. Longer lines are truncated by the
  emitter, never by the reader.

Examples:

```
NOOBIA P1 wifi link.down ssid=Noobia | Noobia Wi-Fi dropped
NOOBIA P1 camera object.seen label=cat conf=0.91 | A cat is in front of the rear camera
NOOBIA P3 touch tap x=540 y=1200 | Screen tapped
NOOBIA P0 battery level pct=71 charging=1 | Battery 71% and charging
NOOBIA P1 mic speech.heard speaker=unknown | Hello Lynx
```

All senses emit through one shared helper, `common/autonomy/sense.py`
(`emit(...)`, plus a `noobia-sense` command for shell services). It
validates the format and writes through syslog.

On a **systemd** host it also sets journald fields: `NOOBIA_P`,
`NOOBIA_SENSE`, `NOOBIA_EVENT`.

On **Lynx** (BusyBox `syslogd`, currently `-l 4`), sense lines are logged at
syslog level `notice`. Install item **I-2** raises syslogd to `-l 6` so
notice lines are kept. Until then a sense line would be dropped. That is a
known blocker, not a bug.

## 2. Trigger (per host, always running, no LLM)

The trigger tails the host's log backend:
- `journalctl -f -o json -t noobia-sense` on systemd;
- `tail -F` of `/var/log/lynx/messages` on Lynx, filtered on the tag.

It cuts **chunks**, closing one when any of these happens:
- a `P1` line arrives (immediate);
- for some `n` ≥ 2, the open chunk holds `n` lines of priority `Pn`;
- the chunk holds more than **15** lines;
- **60 s** have passed since the chunk opened and it holds at least one
  line.

Each closed chunk goes to the regex ranker. The trigger itself never calls
an LLM.

Bounds:
- at most 200 lines and 32 KiB per chunk;
- at most 1 chunk per second to Aigel, and at most 30 per hour per host,
  configurable;
- anything above that is counted and summarized as one line
  (`NOOBIA P0 autonomy chunk.dropped n=…`), never queued without limit.

## 3. Regex ranker (per host, before any LLM call)

The ranker keeps a ranked store of up to **100** patterns per host
(`common/autonomy/patterns/<host>.json`, versioned). Each pattern has:
- an `id` and a `regex`;
- `sense` and `event` filters;
- a `message` template, for example `"A {label} appeared"`;
- a `to_noob` flag: deliver, or just absorb as routine;
- a `cooldown_s`, so a line repeated a million times delivers at most once
  per cooldown;
- `hits` and `last_hit`, plus `origin` (`human` or `aigel`) and `added_at`.

For each chunk:
1. Every line is matched against the patterns in rank order.
2. Matched lines are **explained**. Their messages go to the Noob, subject
   to cooldown, and their hit counts rise.
3. Ranks are re-sorted by recent hits. Below the top 100, the least-used
   patterns retire to an archive file, never silently deleted.
4. Only the **unexplained** lines go on to Aigel. If nothing is left, no LLM
   is called.

Pattern safety, because Python `re` has no timeout:
- at most 200 characters per pattern;
- no back-references and no nested quantifiers (such as `(a+)+`);
- anchored or prefixed by `sense`/`event` filters;
- each new pattern must match its example line and must **not** match a
  fixed corpus of other senses' lines before it is accepted.

Patterns from Aigel are proposals until they pass these checks. They are
recorded with `origin=aigel` and can be reverted.

## 4. Aigel (on Nexus, the LLM in the middle)

Aigel becomes a **service with three channels**:

1. **In:** unexplained chunks from every host's engine, delivered over HTTP
   to Nexus. Authentication follows the existing NRP or Nexus key pattern.
2. **Human:** a local web page on Nexus port **112**, where a person can
   talk to Aigel and see what she has seen and decided. Port 112 is
   privileged, so it needs `CAP_NET_BIND_SERVICE` or a socket unit. That is
   an admin step for Aria or Banshee.
3. **Out:** to the host's Noob: short messages, plus new pattern proposals
   back to that host's ranker.

For each chunk Aigel must choose one of:
- `quiet`: all is fine;
- `message`: one short sentence for the Noob;
- `pattern`: propose a regex so this never needs an LLM again;
- or a combination.

She never acts on hardware herself. Her prompt states that she is
describing the world, not commanding it.

The model is open (decision **D-1** for Noob and Aria). The rules say not to
load another large model next to Dushich's Qwen, and Qwen serves one request
at a time. The trigger bounds keep the rate low, but this still needs a
decision.

## 5. The Noob (Lynx first)

Lynx has three channels:
- **in:** messages from the ranker or Aigel, delivered into her existing
  agent queue (`AGENT_SUBMIT` / `lynx-agent`) as a prompt with a fixed
  prefix (`[sense] …`);
- **in:** a local web page on Lynx;
- **out:** her bounded tools: screen images and animations, flashlight,
  haptics, speaker, and later text-to-speech.

She chooses what to do. The engine never actuates her hardware.

## 6. Safety invariants (non-negotiable)

1. **No feedback loops.** Lines caused by the Noob's own actions carry
   `cause=self`, and the trigger never counts them toward a trigger.
2. **Kill switch.**
   - The file `/etc/noobia/autonomy.disable`, present on a host, stops its
     trigger from delivering anything. The services keep logging.
   - On Lynx, a physical switch (the Alert Slider) is proposed as a second
     override.
3. **Bounded everything:** line, chunk and pattern sizes, rates, queue
   depths, and LLM calls per hour.
4. **Privacy.**
   - Camera frames go to Nexus detection only on Noobia's local network and
     are never stored by default. Only labels and confidences become sense
     lines.
   - Audio becomes text only. Raw audio is not kept.
   - People's speech is shown only as text in the log, the same way Lynx's
     microphone already keeps no audio.
5. **Inspectable.** Every chunk decision (explained, sent to Aigel, Aigel's
   choice, delivered message) is itself logged as a `P0 autonomy` line, so
   anyone can see why a Noob was told something.
6. **Installs on Lynx are Aria's.** Everything is built and tested offline
   first and shipped as install packets.

## 7. Where code lives

| Part | Path | Owner |
| --- | --- | --- |
| Sense helper and command | `common/autonomy/sense.py`, `common/bin/noobia-sense` | Banshee |
| Trigger and chunker | `common/autonomy/trigger.py` | Banshee |
| Regex ranker and pattern store | `common/autonomy/ranker.py`, `common/autonomy/patterns/` | Banshee |
| Contract tests (conformance) | `common/autonomy/test_contract.py` | Gwyn |
| Aigel service, web :112 | `aigel/service/` | Solo Dushich |
| Sense services for Lynx | `lynx/senses/<sense>/` | Solo Dushich (camera detection service on Nexus: Banshee) |
| Delivery into Lynx's agent | `lynx/tools/agent/` (new module) | Gwyn |
| Lynx local web page | `lynx/web/` | Banshee |
| Installs on Lynx | install packets | Aria |

## Open questions for Noob

- **Q1.** "Chunks with their PRIORITY lines stripped off": does this mean
  that lines the regex layer already explained are removed before Aigel
  sees the chunk (this design), or that the `P<n>` markers are removed from
  the text?
- **D-1.** Which model runs Aigel, and on what GPU budget?
