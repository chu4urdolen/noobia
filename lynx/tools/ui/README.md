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

## Tests

```sh
python3 -m unittest discover -s lynx/tools/ui -p 'test_*.py'
```

These 44 tests are all offline. Status fixtures come from the real
`inventory()` functions run over temporary directory trees, and the broker
uses a fake runner.

- **Manifest:** agreement with all 38 source manifests and the phone's
  component lists, source drift, stale committed manifests, every
  `local_calls` file tracked by Git (clean-checkout parity), attended evidence
  rules, and partial or malformed snapshots.
- **Broker:** the exact command list, timeouts, bad JSON, oversized output,
  hostile catalog lines, atomic writes, and install drift.
- **Board:** HTML escaping, and no scripts or controls.
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
