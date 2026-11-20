# Lynx tool presentation (Gwyn's lane)

Owner: Gwyn App Nub. Aria reviews and integrates anything phone-facing.

## `lynx_tool_manifest.py`

Builds a read-only manifest of Lynx's local agent tools from the source pairs in
[`../local_calls/`](../local_calls/) (`<tool>.json` + `<tool>.sh`, installed on
the phone in `/usr/local/share/lynx/agent-tools`). It never contacts Lynx.

For each of the 38 tools it records the description, inputs, timeout, NRP id,
the installed command its wrapper runs, a source hash, and three hand-checked
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

## Tests

```sh
python3 -m unittest discover -s lynx/tools/ui -p 'test_*.py'
```

These are offline. Status fixtures come from the real `inventory()` functions
run over temporary directory trees. The tests check agreement with all 38
source manifests and the phone's component lists, catch source drift and stale
committed manifests, cover partial and malformed snapshots, and assert that no
socket or subprocess is opened.

## Not done yet (completion gate)

A bounded broker that captures the snapshot from Lynx and a UI that renders
it. Neither will open root sockets unprivileged, write to the phone, or
install a service before Aria reviews it.
