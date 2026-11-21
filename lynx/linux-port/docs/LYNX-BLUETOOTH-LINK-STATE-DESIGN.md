# Lynx Bluetooth Link-State Read Architecture and Design

## 1. Platform Identity and Scope

- **Device**: OnePlus Nord 3 5G (CPH2493)
- **SoC / Platform**: MediaTek Dimensity 9000 (MT6983), Project `22823` ("Vitamin")
- **Kernel ABI**: `5.10.149-android12-9-o-g311738fbb5a8`
- **Component**: `hardware/bluetooth` (Status-Only Map Priority 4)
- **Related Routes**:
  - NRP 393 `BT_STATUS` (`lynx/tools/lynx_noob_runtime.py:727`)
  - Bluetooth GATT supervisor (`lynx/tools/lynx_bluetoothd.py`)
  - Bluetooth Acceptance Gate (`lynx/tools/bluetooth/lynx_bt_acceptance_gate.py`)

## 2. Problem Statement and Safety Boundary

The status-only map identifies `hardware/bluetooth` as requiring:
> *"an agent link-state read, then start/stop actions once autostart is proven"*

To prevent inadvertent radio activation, cold-boot hang, or unattended battery drain, strict operational boundaries govern this design:
1. **Strictly Read-Only**: The link-state tool queries runtime telemetry without issuing radio start, stop, connect, or reset commands.
2. **Zero Runlevel Modifications**: `lynx-bluetooth` must NEVER be registered in the default OpenRC runlevel (`rc-update show default`).
3. **No Unauthenticated Pairing**: Pairable mode must remain disabled (`pairable: no`). Bluetooth authentication is decoupled from pairing and relies solely on NRP/1 HMAC-SHA256 frame signatures over GATT.
4. **Offline Evaluation First**: Tooling is driven by deterministic JSON telemetry fixtures and verified via offline unit tests.
5. **Trial Ownership**: Aria owns live trials. No agent may actuate Bluetooth hardware without explicit approval.

## 3. Telemetry Ingestion Architecture

The link-state report synthesizes data across kernel, service, and controller boundaries:

```
+-------------------------------------------------------------+
|                      Lynx Telemetry                         |
+-------------------------------------------------------------+
| Kernel / Dev:      /dev/stpbt, /sys/class/bluetooth/hci0    |
| Modules:           bt_drv_6983, btif_drv, wlan_drv_gen4m_...|
| OpenRC Services:   lynx-bluetooth, bluetooth (BlueZ), dbus   |
| Runtime State:     /run/lynx/bluetooth/ready                |
| Controller:        bluetoothctl show (power, pairable, mac) |
| Active Peers:      bluetoothctl devices Connected           |
| Safety Monitors:   rc-update show default, battery capacity |
+-------------------------------------------------------------+
                              |
                              v
             evaluate_bluetooth_link_state()
                              |
                              v
                 BluetoothLinkStateVerdict
```

### Classification Statuses

| Status | Valid | Radio Powered | Supervisor | Peers | Description |
|---|---|---|---|---|---|
| `RADIO_OFF` | Yes | No | No | 0 | Radio quiescent, controller unpowered, service stopped. |
| `READY_UNLINKED` | Yes | Yes | Yes | 0 | Radio active, GATT service running, awaiting peer attachment. |
| `CONNECTED` | Yes | Yes | Yes | $\ge 1$ | One or more active peer connections established. |
| `DEGRADED` | No | Any | Any | Any | Inconsistent state (e.g. controller up without supervisor). |
| `UNSAFE_CONFIG` | No | Any | Any | Any | Safety violation: service in default runlevel or pairable mode enabled. |
| `ABSENT` | No | No | No | 0 | Telemetry data missing, empty, or unparseable. |

## 4. Safety and Security Invariants

The evaluator strictly audits the following failure invariants:
1. `lynx-bluetooth_in_default_runlevel_forbidden`: Catches regressions where `lynx-bluetooth` is added to `rc-update show default`.
2. `pairable_mode_is_active_expected_disabled`: Refuses configurations where BlueZ has pairable mode enabled.
3. `radio_powered_under_low_battery_threshold_<cap>%`: Refuses active radio state when battery is below 15%.
4. `inconsistent_service_or_controller_state`: Identifies half-open states (e.g., BlueZ running without `lynx-bluetoothd` supervisor or `/run/lynx/bluetooth/ready` missing).

## 5. Tooling and Test Verification

- **Offline Collector / Evaluator**: `lynx/tools/bluetooth/lynx_bluetooth_link_state.py`
- **Unit Test Suite**: `lynx/tools/bluetooth/test_lynx_bluetooth_link_state.py`
- **Test Fixtures**:
  - `fixtures/link-state-radio-off.json`
  - `fixtures/link-state-ready-idle.json`
  - `fixtures/link-state-connected-peer.json`
  - `fixtures/link-state-degraded.json`
  - `fixtures/link-state-unsafe-runlevel.json`
  - `fixtures/link-state-unsafe-pairable.json`

All tests execute completely offline without network or hardware interaction.
