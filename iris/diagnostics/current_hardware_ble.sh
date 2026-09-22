#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
CONFIG=${1:-"$ROOT/tools/iris-tools.conf"}
CTL="$ROOT/tools/irisctl"
"$CTL" --config "$CONFIG" ping
"$CTL" --config "$CONFIG" external-led 0 1
"$CTL" --config "$CONFIG" external-led 2 1
"$ROOT/diagnostics/dht11_ble.sh" "$CONFIG"
"$ROOT/diagnostics/light_ble.sh" "$CONFIG"
"$ROOT/diagnostics/ir_ble.sh" "$CONFIG"
"$ROOT/diagnostics/ultrasonic_ble.sh" "$CONFIG"
