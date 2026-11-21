# Gwyn's Lynx agent and interface queue — 2026-11-21

Noob asked for a substantial queue for Gwyn after his coverage report.
Gwyn is he/him. Lynx is she/her. This queue extends the team handoff and
forge note #83; current forge notes and live evidence take precedence.

Work in order, making one reviewable commit and forge report per item. Before
each item, read `forge-db project get lynx` and touch the project under your
own name with `--together`. Run your own meaningful tests and record exact
commands, results, limits, commit, and confirmed remote hash. Check the
shared tree before Git operations, and stage only your files. Coordinate
before editing a source area another agent has begun.

## 1. Agent cancellation contract and offline tool

The coverage report found that `lynx_codex` has no agent-facing stop tool,
although NRP `AGENT_CANCEL` exists. Trace its request, authorization, job-ID
scope, and result semantics. If safe, implement an offline-tested cancel
wrapper and manifest under `lynx/tools/agent/` and
`lynx/tools/local_calls/`, including tests for invalid IDs, missing jobs,
already-finished jobs, timeout, and unauthorized callers. If the NRP route
cannot safely expose cancellation, deliver a source-cited no-go analysis
instead. Do not deploy to Lynx, cancel a real job, or alter the live queue.
Aria reviews before phone installation.

## 2. Status-only hardware tool contract map

Turn the 15 status-only components in `lynx_tool_coverage.py` into a
prioritized, source-cited implementation map in `lynx/tools/ui/`. For each,
say whether a useful read/action function already exists through NRP or
another safe route, what agent wrapper is missing, what stop/status companion
an action needs, and what physical proof is absent. Distinguish a genuinely
missing tool from an unloaded driver. Deliver machine-readable and human
readable output with fixture tests. Do not implement another owner's USB,
modem, camera, or health hardware wrapper in this item.

## 3. Snapshot age and boot-change guard

Extend the read-only board and coverage report so old snapshots cannot look
current. Show capture time, age, boot ID when present, and a clear stale or
different-boot state; never convert historical attended evidence into live
validation. Use saved fixtures only, including clock skew, missing time,
malformed time, and changed boot cases. Keep the board script-free and free
of controls that could act on Lynx.

## 4. Source-to-installed catalog diff

Make catalog drift actionable without leaking private content. From a saved
snapshot, report the exact tool names missing, added, or hash-different,
with bounded output and a deterministic JSON/text format. Verify against a
clean checkout and fixtures for a partial catalog, hostile names, duplicates,
and unchanged 38/38 state. No phone writes or automatic sync.

## 5. Accessible static board

Audit the board at desktop, narrow phone width, dark mode, keyboard, and
screen-reader structure. Fix concrete contrast, focus, heading, table/list,
or stale-state clarity problems found. Preserve escaped text and no script,
forms, remote assets, or action buttons. Record browser/automated evidence
and test results. Do not claim physical hardware validation from a UI check.

## 6. Portable health view, after Dushich's collector contract stabilizes

Consume Dushich's documented health JSON as an optional saved input to a
read-only board section. Preserve `unknown`, `warn`, and `fail`; do not invent
missing values or turn suggested thresholds into validated Lynx limits.
Use offline fixtures and tests; do not edit `lynx/tools/health/`, run a
periodic health job, or install a phone service. If the collector schema is
still changing, record the blocked dependency and move to item 7.

## 7. On-demand operator entry point

Provide one bounded Nexus-side command that refreshes the existing status
snapshot, checks catalog drift, and renders the static board, returning a
short result with output path, source failures, and snapshot age. Reuse the
existing pinned SSH broker; do not add a new transport. Tests must cover
offline fixture mode, SSH timeout/failure, partial status, and atomic output.
No periodic service, browser server, or phone install.

## Shared boundaries

- Banshee owns USB, fingerprint, NFC and modem analysis; Dushich owns
  `lynx/tools/health/`; Aria owns live hardware trials and deployment.
  Do not edit their source areas without an explicit forge coordination note.
- No SIM is installed. No modem start, RF actuation, module load, phone
  service installation, boot/storage write, or unattended physical trial is
  authorized by this queue. GNSS position testing remains last.
- A precise blocked result with missing evidence is acceptable. Every
  claimed success needs its own command, test or receipt, and limitation.
