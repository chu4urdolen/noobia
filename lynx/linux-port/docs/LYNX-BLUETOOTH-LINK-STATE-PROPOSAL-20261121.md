# Lynx Bluetooth Link-State Catalog Proposal (B6)

## 1. Overview and Platform Context

- **Device**: OnePlus Nord 3 5G (CPH2493)
- **Platform**: MediaTek Dimensity 9000 (MT6983), Project `22823` ("Vitamin")
- **Target Component**: `hardware/bluetooth` (Status-Only Map Priority 4)
- **Proposal Status**: Catalog-ready proposal staged in [`lynx/tools/bluetooth/catalog_proposal/`](file:///noobia/lynx/tools/bluetooth/catalog_proposal/).
- **Boundary**: In accordance with Gwyn's review instructions, this tool is **not** added to `lynx/tools/local_calls/` until Aria approves deployment.

---

## 2. Motivation and Coverage Impact

The status-only map ([`lynx/tools/ui/status_only_map.json`](file:///noobia/lynx/tools/ui/status_only_map.json)) classifies `hardware/bluetooth` as:
```json
{
  "component": "hardware/bluetooth",
  "priority": 3,
  "kind": "trial_needed",
  "owner": "Aria",
  "missing_tool": "an agent link-state read, then start/stop actions once autostart is proven"
}
```

In [`lynx_tool_coverage.py`](file:///noobia/lynx/tools/ui/lynx_tool_coverage.py), a component is marked `status_only` if it has a status tool but neither a read tool nor an action tool:
```python
elif not (entry["read_tools"] or entry["action_tools"]):
    status_only.append(key)
```

By providing `lynx_bluetooth_link_state` as a companion read tool (`effect="read_only"`, `reports_component_status=False`), `hardware/bluetooth` gains an active `read_tools` entry, resolving the missing read tool requirement and advancing the component along the acceptance pipeline.

---

## 3. Tool Definition and Schema

### 3.1 Tool Schema (`lynx_bluetooth_link_state.json`)
Staged at [`lynx/tools/bluetooth/catalog_proposal/lynx_bluetooth_link_state.json`](file:///noobia/lynx/tools/bluetooth/catalog_proposal/lynx_bluetooth_link_state.json):
```json
{
  "name": "lynx_bluetooth_link_state",
  "description": "Entity: Lynx. Read bluetooth controller power, OpenRC supervisor status, runlevel autostart safety, and active connected peer topologies without radio actuation.",
  "inputSchema": {
    "type": "object",
    "properties": {},
    "required": [],
    "additionalProperties": false
  },
  "timeout": 10
}
```

### 3.2 Executable Wrapper (`lynx_bluetooth_link_state.sh`)
Staged at [`lynx/tools/bluetooth/catalog_proposal/lynx_bluetooth_link_state.sh`](file:///noobia/lynx/tools/bluetooth/catalog_proposal/lynx_bluetooth_link_state.sh):
```sh
#!/bin/sh
# Entity: Lynx. Read-only Bluetooth link-state evaluation.
exec /usr/bin/python3 /usr/local/bin/lynx-bluetooth-link-state
```

---

## 4. Manifest Entry Specification

For incorporation into [`lynx-tool-manifest.json`](file:///noobia/lynx/tools/ui/lynx-tool-manifest.json) upon Aria's approval:
```json
{
  "name": "lynx_bluetooth_link_state",
  "description": "Entity: Lynx. Read bluetooth controller power, OpenRC supervisor status, runlevel autostart safety, and active connected peer topologies without radio actuation.",
  "effect": "read_only",
  "group": "radio",
  "status_source": "hardware",
  "component": "bluetooth",
  "reports_component_status": false,
  "also_components": [],
  "attended": [],
  "inputs": [],
  "required_inputs": [],
  "timeout_s": 10,
  "entry": {
    "command": "lynx-bluetooth-link-state",
    "args": []
  }
}
```

---

## 5. Effect Classification for Gwyn's Coverage Table

In [`lynx/tools/ui/lynx_tool_manifest.py`](file:///noobia/lynx/tools/ui/lynx_tool_manifest.py), the tool maps to the following tuple in `TOOLS`:
```python
"lynx_bluetooth_link_state": ("read_only", "radio", ("hardware", "bluetooth"), False),
```

### Classification Breakdown:
- **`effect`**: `"read_only"` (Audits and evaluates controller power, OpenRC service status, runlevel safety, and connected peer list; issues zero radio start/stop commands).
- **`group`**: `"radio"` (Placed under radio tooling alongside `lynx_bluetooth`, `lynx_wifi_status`, and `lynx_cellular_status`).
- **`component`**: `("hardware", "bluetooth")` (Maps directly to the MediaTek Bluetooth connectivity subsystem).
- **`reports`**: `False` (Acts as a deep link-state reader companion rather than the primary unitary hardware status command).
- **`coverage_role`**: `read_tools` (Populates `components["hardware/bluetooth"]["read_tools"]`).

---

## 6. Verification and Boundary Enforcement

- Unit tests in [`test_lynx_bluetooth_proposal.py`](file:///noobia/lynx/tools/bluetooth/test_lynx_bluetooth_proposal.py) verify schema integrity, wrapper syntax, manifest keys, and coverage role mappings.
- The test suite explicitly asserts that `lynx/tools/local_calls/` remains unmodified (`test_local_calls_boundary_enforced`), guaranteeing that no unapproved catalog changes occur until Aria authorizes deployment.
