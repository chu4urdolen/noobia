# Lynx Bluetooth Tools

This directory contains validation, telemetry evaluation, and acceptance tooling for Bluetooth on the OnePlus Nord 3 5G CPH2493 (MediaTek MT6983, Project 22823 "Vitamin").

## Tools Overview

### 1. Bluetooth Acceptance Gate (`lynx_bt_acceptance_gate.py`)
Enforces strict acceptance criteria on Bluetooth trial receipts without issuing network calls or device mutations:
- **Fresh Boot ID**: Proves evidence originates from a new boot cycle rather than stale logs or prior sessions.
- **Sustained System Health**: Enforces unbroken healthy status samples across the trial hold (zero issues, battery $\ge 15\%$, temperature $< 55^\circ\text{C}$).
- **Verified Radio Teardown**: Confirms radio power-off at trial completion (`rc-service lynx-bluetooth stop` succeeded, `hci0` removed).
- **Bounded Recovery Boundary**: Proves zero partition writes, zero runlevel alterations, and disarmed watchdogs.

### 2. Bluetooth Link-State Evaluator (`lynx_bluetooth_link_state.py`)
Provides an agent-facing, read-only link-state report on top of `BT_STATUS` (NRP 393) and `lynx_bluetoothd.py`:
- **State Classification**: Classifies telemetry into `RADIO_OFF`, `READY_UNLINKED`, `CONNECTED`, `DEGRADED`, `UNSAFE_CONFIG`, and `ABSENT`.
- **Peer Topology**: Surfaces active connected BLE/BT peers (MAC addresses, device names, connection flags).
- **Safety Auditing**: Audits default OpenRC runlevels (ensuring `lynx-bluetooth` is not autostarted) and validates `pairable` mode is disabled.
- **Read-Only / Live Gating**: Strictly offline evaluator with optional read-only live query requiring explicit `--live --allow-live`.

### 3. Catalog Proposal (`catalog_proposal/`)
Maintains the staged MCP tool schema (`lynx_bluetooth_link_state.json`), executable wrapper script (`lynx_bluetooth_link_state.sh`), manifest entry, and coverage mapping. Awaiting Aria's approval before installation into `lynx/tools/local_calls/`.

## Usage

```bash
# Evaluate a Bluetooth trial receipt
python3 lynx_bt_acceptance_gate.py fixtures/passing-trial-receipt.json --reference-boot-id "<prior-boot-uuid>"

# Evaluate a link-state telemetry fixture
python3 lynx_bluetooth_link_state.py fixtures/link-state-radio-off.json

# Run unit tests
python3 -m unittest discover -s . -p 'test_*.py'
```
