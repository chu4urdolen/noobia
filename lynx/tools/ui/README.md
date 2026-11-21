# Lynx tool presentation (Gwyn's lane)

Owner: Gwyn App Nub. Aria reviews and integrates anything phone-facing.

## `lynx_tool_manifest.py`

Builds a read-only manifest of Lynx's local agent tools from the source pairs in
[`../local_calls/`](../local_calls/) (`<tool>.json` + `<tool>.sh`, installed on
the phone in `/usr/local/share/lynx/agent-tools`). It never contacts Lynx.

For each of the 38 tools it records the description, inputs, timeout, NRP id,
the installed command its wrapper runs, per-file SHA-256 hashes, and three hand-checked
classifications:

- **effect**: `read_only`, `samples_microphone`, `actuates`, `stops`, or
  `runs_task`. A new tool with no classification is an error. It is never
  quietly shown as read-only.
- **status component**: which `lynx-platform-status`, `lynx-peripheral-status`
  or `lynx-hardware` component the tool reports on or depends on.
- **reports_component_status**: whether the tool's output *is* that status.

**Interface inventory is not proof of function.** The offline manifest carries
no validation at all. Live state appears only when you join a saved status
snapshot:

```sh
lynx/tools/ui/lynx_tool_manifest.py                      # offline JSON manifest
lynx/tools/ui/lynx_tool_manifest.py --summary            # one line per tool
lynx/tools/ui/lynx_tool_manifest.py --status snap.json   # join a saved snapshot
lynx/tools/ui/lynx_tool_manifest.py --write              # regenerate lynx-tool-manifest.json
lynx/tools/ui/lynx_tool_manifest.py --check              # exit 1 if the committed copy is stale
```

A snapshot is a JSON object with any of `platform`, `peripheral`, `hardware`
(the output of each status command's `all`) and optional `captured_at`. Each
tool then gets `live.state`:

| State | Meaning |
| --- | --- |
| `validated` | The phone's status code says the function is proven |
| `interface_only` | Kernel interface present, function not proven |
| `not_ready` | Interface absent or unhealthy |
| `unknown` | No snapshot for that component, or the tool has no status component |
| `malformed` | Snapshot entry lacks boolean `interface_ready`/`validated` |

Aggregate tools (`lynx_platform_status`, `lynx_peripheral_status`) get a
`summary` with state counts.

`validated` mirrors only what the phone's status code computes. Several
components (touch, haptic, audio, camera) have human-attended confirmations in
forge notes and handoff docs, but their status code still reports
`validated: false`. The manifest does not override that. Whether attended
evidence should feed the status code belongs to Aria's lane.

## `lynx_status_snapshot.py`: the status broker

Captures one snapshot from Lynx over the pinned Alpine SSH link (the
`lynx_remote.py` route) by running a **fixed** list of read-only commands:
`lynx-platform-status all`, `lynx-peripheral-status all`,
`lynx-hardware status all`, and `sha256sum` of the installed agent-tool
catalog. No caller input reaches the remote shell. Each command has a 10 s
remote and 20 s local timeout and a 256 KiB cap, and per-source failures are
recorded, not hidden. The snapshot goes atomically to `state/latest.json`, which
Git ignores. Exit codes: 0 all captured, 2 partial, 1 nothing.

The SSH login is root, so this list must stay read-only. It writes nothing
to the phone, loads nothing, and never touches the modem or SIM.

With the catalog hashes, each tool also gets `installed`: `current`,
`differs`, `missing` or `unknown`, and the snapshot lists tools installed on
the phone but absent from source.

## `lynx_tool_board.py`: the board

```sh
lynx/tools/ui/lynx_tool_board.py --refresh   # capture, then render state/board.html
lynx/tools/ui/lynx_tool_board.py             # re-render from the saved snapshot
```

A self-contained HTML page with no scripts, forms, or network loads. It shows
component chips, then one card per tool grouped by area. Each card has
badges for effect, proven/unproven state, and install drift, plus the
status code's "next" hint. It shows snapshot age, and warns when sources fail
or the installed catalog drifts. It cannot act on Lynx. Checked with
Playwright at desktop, phone (390 px) and dark-mode sizes.

## Attended confirmations (`attended_evidence.json`)

Phone-reported validation and human confirmations stay separate. The status
code's `validated` flag drives the chips and each card's state badge. A person
seeing, hearing, or feeling one specific function is recorded separately in
`attended_evidence.json`. Each entry has a component, the specific `tools` it
covers, the observer, the date, the boot if known, receipts, and a
`does_not_establish` list. The loader rejects entries without receipts,
limits, or tools, and tools that belong to another component. Such entries
add a blue "attended" badge and a line to only the named cards, plus a
separate "Attended confirmations" section. They never change `live`. They are
history and may not hold on the current boot.

Current entries: speaker beep and an 80 ms haptic pulse (2026-11-21,
`45a1ecf`), one rear LED pulse (2026-11-02), a microphone clap response
(2026-10-29), and the USB ACM link (2026-11-21, forge notes #58 and #67).
Touch and cameras are deliberately absent. No receipt records a person
confirming touch input. The camera frames were judged recognizable, but no
record names an attending observer. Per Aria's note #61, add entries only with
a specific receipt.

## `lynx_tool_coverage.py`: coverage audit

A read-only gap report built from the tracked manifest, the attended file, and
a saved snapshot. It never contacts Lynx. To audit live state, capture first
with `lynx_status_snapshot.py`.

```sh
lynx/tools/ui/lynx_tool_coverage.py --text           # uses state/latest.json if present
lynx/tools/ui/lynx_tool_coverage.py --status FILE    # JSON for a specific snapshot
lynx/tools/ui/lynx_tool_coverage.py --no-status      # source-only; every phone state is unknown
```

For each of the 20 components, plus `agent/*` for the agent tools, it lists
the status, read, action and stop tools, the phone state, and attended IDs.
Gaps:

- **components without tools** and **status-only components** (no separate
  read or action tool, e.g. camera, gnss, bluetooth, nfc);
- **actions missing companions**: every `actuates`/`runs_task` tool needs a
  stop tool and a read-only status in its component;
- **catalog drift**: tools that differ from source, tools missing on the
  phone, and tools installed only on the phone;
- **unverified**: phone state not `validated`, with earlier-success evidence
  flags and attended IDs listed beside it, never merged into it;
- **not ready**, with a cause: `no_tool_source`, `tool_not_installed`,
  `driver_not_loaded` (a driver flag is false on this boot), or
  `interface_absent`. A false driver flag does not prove a driver ever worked.
  Earlier success is shown separately.

The 2026-11-21 result from the 23:55 UTC snapshot:
- No component lacks a tool, and installed copies show no drift.
- `lynx_codex` has no stop tool. It kills itself after 120 s, but NRP's
  `AGENT_CANCEL` has no agent tool.
- Flashlight, gnss, camera and fingerprint have no driver loaded on this boot.
  Only flashlight (visual confirmation) and gnss (NMEA trial) record earlier
  success.
- The SIM interface is absent.

## `lynx_status_only_map.py`: what each status-only part still needs

`status_only_map.json` is a curated map of the 15 status-only components, with
a source citation for every route. The command checks it against the coverage
audit and fails if the map is stale. It adds phone state, attended IDs, and
whether the driver is loaded on this boot.

```sh
lynx/tools/ui/lynx_status_only_map.py --text
```

Each component's gap is one of:
- `missing_tool`: a safe route exists and only the agent tool is missing;
- `trial_needed`: a reviewed live trial must come first;
- `blocked`;
- `none`: the status read is the function.

`driver_loaded_this_boot=false` is reported separately. It is neither a
missing tool nor proof that a driver ever worked.

Current order:
1. **Touch (missing tool).** `TOUCH_STATUS`/`TOUCH_POLL` exist, but
   `TOUCH_POLL` consumes events, so a wrapper needs Aria's agreement.
2. **Display (missing tool).** Image play and stop already exist through the
   media tools but are classified under audio.
3. **Headset, Bluetooth, camera, GNSS, NFC, USB, fingerprint (trial needed).**
4. **Cellular and SIM (blocked).**
5. **Battery, thermal, storage, Wi-Fi (no gap).**

## Snapshot age and boot guard (`lynx_snapshot_age.py`)

Each snapshot now also records Lynx's kernel boot ID
(`/proc/sys/kernel/random/boot_id`, a fifth fixed read-only command). When it
is saved, the previous snapshot's boot ID and time go under `previous`.

The board and the coverage report classify every snapshot:
- `fresh`: at most 15 minutes old;
- `stale`;
- `future`: more than 2 minutes ahead, meaning a clock problem;
- `unknown_time`;
- `malformed_time`.

They also report the boot as `same_as_previous`, `changed_since_previous`,
`no_previous`, or `unknown`. A snapshot that is not fresh, or comes after a
reboot, gets a warning banner, and the component heading changes to "as
captured, not current". Validation is never altered.

Each attended entry says whether it was on the same boot as the snapshot.
Even then it is "still history, not a live check". For reproducible output,
`lynx_tool_coverage.py --now YYYY-MM-DDTHH:MM:SSZ` fixes the clock.

## `lynx_catalog_diff.py`: source versus installed tools

Compares tracked `local_calls` pairs with the installed catalog hashes in a
saved snapshot. For each file it reports `same`, `differs`,
`missing_on_phone`, or `added_on_phone`, and gives each tool one status:
`in_sync`, `hash_differs`, `missing_on_phone`, `added_on_phone`, or `partial`.

The output holds names and 12-character hash prefixes only, never file
contents. It is bounded (`--limit`, default 50, with exact counts) and sorted.
Hostile names are counted, with at most a 40-character escaped preview.
Duplicate keys in the snapshot are reported; the snapshot capture now
rejects duplicate catalog lines.

```sh
lynx/tools/ui/lynx_catalog_diff.py --text            # IN SYNC / DRIFT
lynx/tools/ui/lynx_catalog_diff.py --fail-on-drift   # exit 2 on drift
```

It never syncs or writes. 2026-11-21 00:10 UTC: IN SYNC, 38/38.

## Accessibility (`check_board_a11y.py`)

The checker runs in a real browser, in light and dark mode at 1200 px and
390 px wide. It measures:
- WCAG contrast of every text element;
- the heading outline;
- landmarks;
- Tab order and whether focus is visible;
- horizontal overflow;
- forbidden or remote elements.

It exits 1 on any failure and checks only the page, never hardware.

```sh
PLAYWRIGHT_BROWSERS_PATH=$NOOBIA/common/runtime/playwright \
  $NOOBIA/common/runtime/web-venv/bin/python lynx/tools/ui/check_board_a11y.py BOARD.html
```

Fixed on 2026-11-21, after the audit:
- Cards were bare `div`s. They are now list items in labelled `section`s,
  with spoken tool counts.
- Badges were an unlabelled run of words. Hidden labels now read "Effect",
  "Phone state", "Install", and "Human check".
- The footer sat inside `main`. It is now outside.
- The page had nothing to focus. An in-page section `nav` now has a visible
  3 px focus ring.
- On a stale page, every state badge now says "(as captured)".
- The green badge contrast went from 4.63:1 to at least 5.24:1, with muted
  text darkened.

Result on the live board and a 5-hour-stale rendering: no failures in all 4
views. Minimum contrast is 5.24:1 in light mode and 6.2:1 in dark. All 13
links are reached by Tab with visible focus. No overflow at 390 px. There is
still no script, form, button, input, or remote asset.

## Health section (`lynx_health_view.py`)

`lynx_tool_board.py --health FILE` adds an optional section from a **saved**
`portable-health/1` report. Without `--health` it uses `state/health.json` if
that exists. The report comes from Dushich's
`lynx/tools/health/portable_health.py` or `lynx_health_collect.py --evaluate`.
The board never runs his collector or evaluator, and never edits
`lynx/tools/health/`.

How it reads the report:
- `ok`, `warn`, `fail` and `unknown` are shown exactly. Anything else is
  `unrecognized`, never ok.
- The verdict carries a count of unknown checks.
- Missing values stay missing.
- The section states that thresholds are Dushich's proposals, not validated
  Lynx limits.
- Stale or offset-timestamped reports are aged correctly.
- A report with the wrong schema or host is explained, not shown.

Health never changes the phone-reported validation.

## Tests

```sh
python3 -m unittest discover -s lynx/tools/ui -p 'test_*.py'
```

These 95 tests are all offline. Status fixtures come from the real
`inventory()` functions run over temporary directory trees, and the broker
uses a fake runner.

- **Manifest:** agreement with all 38 source manifests and the phone's
  component lists, source drift, stale committed manifests, every
  `local_calls` file tracked by Git (clean-checkout parity), attended evidence
  rules, and partial or malformed snapshots.
- **Broker:** the exact command list, timeouts, bad JSON, oversized output,
  hostile catalog lines, atomic writes, and install drift.
- **Board:** HTML escaping, and no scripts or controls.
- **Status-only map:** agreement with the coverage audit, every cited path
  exists, cited NRP line numbers name the right functions, staleness and
  bad-entry rejection, and driver state kept apart from gaps.
- **Age and boot guard:** fresh, stale, clock skew, missing and malformed
  time, changed or unknown boot, previous-boot recording, the stale banner,
  attended boot relation, and no scripts.
- **Catalog diff:** 38/38 unchanged, partial catalog, phone-only tools,
  hostile names, duplicate keys and lines, bounded deterministic output, exit
  codes, and no file contents.
- **Board structure:** one h1 and no skipped heading levels, landmarks,
  footer outside `main`, cards as list items in labelled sections, in-page
  links only, spoken badge labels, and "(as captured)" on every known state
  when stale.
- **Health section:** statuses preserved and the unknown count shown,
  unrecognized values never ok, no invented values, wrong schema or host
  rejected, bounded output, stale and offset times, escaping, and a bad file
  still renders a board. It uses Dushich's own evaluator on his tracked
  examples, read-only.
- **Coverage:** companion rules, missing tools, the different not-ready
  causes, drift, keeping attended evidence separate, and JSON output that
  repeats exactly for the same input.

## Known gaps

- Banshee routed the Nexus `noobia` MCP's Lynx status tools over pinned SSH
  in `c3afc9f`. Before that they ran on Nexus and failed.
- The status code reports touch, haptic and audio `validated: false` despite
  attended confirmations. The board mirrors the code.
- `lynx_agent_health.sh` checks for `/usr/local/bin/lynx-agent`, whose source
  `lynx/tools/agent/lynx_agent.py` is still untracked. That file is Aria's.
  The manifest does not need it.
- A periodic refresh would be a service install, so it waits for Aria's
  review.
