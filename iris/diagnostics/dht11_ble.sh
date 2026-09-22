#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
CTL="$ROOT/tools/irisctl"
CONFIG=${1:-"$ROOT/tools/iris-tools.conf"}
[[ ! -r $CONFIG ]] || source "$CONFIG"
SAMPLES=${IRIS_DIAG_SAMPLES:-3}
PAUSE=${IRIS_DIAG_PAUSE_SECONDS:-2.1}
cleanup() {
  "$CTL" --config "$CONFIG" external-led 0 0 || true
  "$CTL" --config "$CONFIG" external-led 2 0 || true
}
trap cleanup EXIT
"$CTL" --config "$CONFIG" external-led 0 1
"$CTL" --config "$CONFIG" external-led 2 1
failures=0
for ((sample = 1; sample <= SAMPLES; ++sample)); do
  "$CTL" --config "$CONFIG" dht-read || failures=$((failures+1))
  sleep "$PAUSE"
done
"$CTL" --config "$CONFIG" ping
test "$failures" -eq 0
