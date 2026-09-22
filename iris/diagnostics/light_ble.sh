#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
CTL="$ROOT/tools/irisctl"
CONFIG=${1:-"$ROOT/tools/iris-tools.conf"}
[[ ! -r $CONFIG ]] || source "$CONFIG"
SAMPLES=${IRIS_DIAG_SAMPLES:-3}
ADC_SAMPLES=${IRIS_LIGHT_ADC_SAMPLES:-16}
# Leave both LEDs on as requested; readings are raw ADC counts, not lux.
"$CTL" --config "$CONFIG" external-led 0 1
"$CTL" --config "$CONFIG" external-led 2 1
for ((sample = 1; sample <= SAMPLES; ++sample)); do
  "$CTL" --config "$CONFIG" light-read "$ADC_SAMPLES"
  sleep 1
done
"$CTL" --config "$CONFIG" ping
