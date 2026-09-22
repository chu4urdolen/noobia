#!/usr/bin/env bash
# Address-only OLED check, no display commands. Leaves I2C closed.
# ESP-IDF 5.5.5 probes at 100 kHz regardless of configured data-write speed.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
CTL="$ROOT/tools/irisctl"
HZ=${1:-${IRIS_I2C_HZ:-100000}}
if [[ $# -gt 1 || ! $HZ =~ ^[0-9]+$ ]] || (( 10#$HZ < 10000 || 10#$HZ > 400000 )); then
  echo 'usage: oled_17_18_ble.sh [frequency: 10000..400000]' >&2
  exit 2
fi
cleanup() { "$CTL" ble oled_cleanup CALL I2C_CLOSE || true; }
trap cleanup EXIT
"$CTL" ble oled_info INFO
"$CTL" ble oled_start CALL I2C_CONFIG "$HZ"
"$CTL" ble oled_lines CALL I2C_LINES
"$CTL" ble oled_addresses CALL I2C_SCAN 60 61
"$CTL" ble oled_close CALL I2C_CLOSE
"$CTL" ble oled_released CALL I2C_LINES
"$CTL" ble oled_alive PING
trap - EXIT
