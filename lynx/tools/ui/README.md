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

## Tests

```sh
python3 -m unittest discover -s lynx/tools/ui -p 'test_*.py'
```

These 27 tests are all offline. Status fixtures come from the real `inventory()`
functions run over temporary directory trees, and the broker uses a fake
runner. The tests check agreement with all 38 source manifests and the phone's
component lists, catch source drift and stale committed manifests, and cover
partial and malformed snapshots. For the broker they cover the exact command
list, timeouts, bad JSON, oversized output, hostile catalog lines, atomic
writes, and install drift. For the board they check HTML escaping and that
the page has no scripts or controls.

## Known gaps

- The Nexus `noobia` MCP loads these phone-side wrappers and runs them on
  Nexus, where `/usr/local/bin/lynx-*` does not exist, so
  `lynx_platform_status` and similar tools fail there. Banshee owns that MCP.
- The status code reports touch, haptic and audio `validated: false` despite
  attended confirmations. The board mirrors the code.
- Git does not track 6 of the 76 source files (`lynx_agent_health`,
  `lynx_codex`, `lynx_queue_health`).
- A periodic refresh would be a service install, so it waits for Aria's
  review.
