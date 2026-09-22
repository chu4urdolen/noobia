#!/usr/bin/env bash
# Remote, bounded hardware-I2C test. Bus is closed on exit.
set -u
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
CTL="$ROOT/tools/irisctl"
HZ=${1:-${IRIS_I2C_HZ:-100000}}
close_bus() { "$CTL" ble i2c_cleanup CALL I2C_CLOSE >/dev/null 2>&1 || true; }
trap close_bus EXIT

"$CTL" ble i2c_ping_before PING || exit 1
# Prove the compiled service has not initialized the bus at boot.
if "$CTL" ble i2c_before CALL I2C_SCAN; then
  echo "I2C_SCAN unexpectedly succeeded before I2C_CONFIG" >&2
  exit 1
fi
"$CTL" ble i2c_start CALL I2C_CONFIG "$HZ" || exit 1
"$CTL" ble i2c_scan CALL I2C_SCAN || exit 1
"$CTL" ble i2c_ping_after_scan PING || exit 1
"$CTL" ble i2c_close CALL I2C_CLOSE || exit 1
"$CTL" ble i2c_after_close CALL I2C_SCAN && {
  echo "I2C_SCAN unexpectedly succeeded after I2C_CLOSE" >&2
  exit 1
}
"$CTL" ble i2c_mic_after CALL MIC_LEVEL || exit 1
"$CTL" ble i2c_camera_after CALL CAMERA_CAPTURE || exit 1
"$CTL" ble i2c_alive PING || exit 1
