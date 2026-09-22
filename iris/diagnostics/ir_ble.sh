#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
CONFIG=${1:-"$ROOT/tools/iris-tools.conf"}
[[ ! -r $CONFIG ]] || source "$CONFIG"
"$ROOT/tools/irisctl" --config "$CONFIG" ir-test "${IRIS_IR_BURSTS:-20}"
