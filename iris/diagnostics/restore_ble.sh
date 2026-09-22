#!/usr/bin/env bash
# Uses the existing BLE bridge; replaces the current VM, leaves RSSI off.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
CTL="$ROOT/tools/irisctl"
"$CTL" ble verify_ping PING
"$CTL" ble verify_info INFO
"$CTL" ble verify_sd CALL STORAGE_STATUS
"$CTL" ble verify_mic CALL MIC_LEVEL
"$CTL" ble verify_load LOAD 0100070000000101050000000302000100
"$CTL" ble verify_run RUN
"$CTL" ble verify_status STATUS
"$CTL" ble verify_wait LOAD 01002a00000021e803100600
"$CTL" ble verify_wait_run RUN
"$CTL" ble verify_wait_status STATUS
"$CTL" ble verify_stop STOP
"$CTL" ble verify_replace LOAD 0100050000000101030000000302000100
"$CTL" ble verify_replace_run RUN
"$CTL" ble verify_replace_status STATUS
"$CTL" ble verify_alive PING
