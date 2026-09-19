#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
CTL="$ROOT/tools/irisctl"
# Leave both LEDs on as requested; readings are raw ADC counts, not lux.
"$CTL" external-led 0 1
"$CTL" external-led 2 1
for sample in 1 2 3 4 5; do
  "$CTL" light-read 16
  sleep 1
done
"$CTL" ping
