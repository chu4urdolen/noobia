#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
CTL="$ROOT/tools/irisctl"
cleanup() {
  "$CTL" external-led 0 0 || true
  "$CTL" external-led 2 0 || true
}
trap cleanup EXIT
"$CTL" external-led 0 1
"$CTL" external-led 2 1
failures=0
for sample in 1 2 3; do
  "$CTL" dht-read || failures=$((failures+1))
  sleep 2.1
done
"$CTL" ping
test "$failures" -eq 0
