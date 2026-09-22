#!/usr/bin/env bash
# Two bounded display-off writes; no initialization, RAM writes, or retries.
# Unlike address-only probes, Wire data writes use the selected 10 kHz clock.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
CTL="$ROOT/tools/irisctl"
HZ=${1:-${IRIS_I2C_SLOW_HZ:-10000}}
cleanup() {
  "$CTL" ble oled_slow_cleanup CALL I2C_CLOSE || true
  "$CTL" ble oled_slow_alive PING || true
}
trap cleanup EXIT
"$CTL" ble oled_slow_start CALL I2C_CONFIG "$HZ"
"$CTL" ble oled_slow_lines CALL I2C_LINES
for address in 60 61; do
  # SH1107: command control 0x00, display off 0xAE.
  if reply=$("$CTL" ble "oled_slow_$address" CALL I2C_WRITE "$address" 0 174 2>&1); then
    printf '%s\n' "$reply"
  else
    printf '%s\n' "$reply"
    # Continue only on an explicit native NACK, not a lost BLE connection.
    [[ $reply == *'ERR'*'I2C write error code=2'* ]] || exit 1
  fi
done
"$CTL" ble oled_slow_close CALL I2C_CLOSE
"$CTL" ble oled_slow_released CALL I2C_LINES
"$CTL" ble oled_slow_alive PING
trap - EXIT
