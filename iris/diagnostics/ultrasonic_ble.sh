#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
CONFIG=${1:-"$ROOT/tools/iris-tools.conf"}
[[ ! -r $CONFIG ]] || source "$CONFIG"
"$ROOT/tools/irisctl" --config "$CONFIG" ultrasonic-read \
  "${IRIS_ULTRASONIC_SAMPLES:-3}" "${IRIS_ULTRASONIC_TIMEOUT_US:-30000}"
