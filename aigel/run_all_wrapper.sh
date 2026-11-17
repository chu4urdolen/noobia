#!/usr/bin/env bash
set -euo pipefail

# ------------------------------------------------------------------
# 1. Configuration defaults
# ------------------------------------------------------------------
CONFIG_FILE="/noobia/aigel/config.json"
DEFAULT_INTERVAL_MS=100
DEFAULT_PERIOD_S=300
REALTIME=0
DURATION=0

# ------------------------------------------------------------------
# 2. Parse CLI args
# ------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --interval) DEFAULT_INTERVAL_MS=$2; shift 2;;
    --period)   DEFAULT_PERIOD_S=$2;   shift 2;;
    --real-time) REALTIME=1; shift;;
    --duration) DURATION=$2; shift 2;;
    *) echo "Unknown option: $1"; exit 1;;
  esac
done

# Override with config.json if present and not overridden
if [[ -f "$CONFIG_FILE" ]]; then
  [[ -z ${DEFAULT_INTERVAL_MS:+set} ]] && DEFAULT_INTERVAL_MS=$(jq -r '.sample_interval_ms' "$CONFIG_FILE")
  [[ -z ${DEFAULT_PERIOD_S:+set}   ]] && DEFAULT_PERIOD_S=$(jq -r '.sample_period_s' "$CONFIG_FILE")
fi

echo "Running all Aigel diagnostics with:" 
echo "  Interval = ${DEFAULT_INTERVAL_MS} ms"
echo "  Period   = ${DEFAULT_PERIOD_S} s"
[[ $REALTIME -eq 1 ]] && echo "  Real‑time output = ON"
[[ $DURATION -gt 0 ]] && echo "  Duration      = ${DURATION}s"

# ------------------------------------------------------------------
# 3. Prepare environment
# ------------------------------------------------------------------
SERVICES_DIR="/noobia/common/services"

# Ensure log dir exists and is owned by aria
mkdir -p /var/log/noobia
mkdir -p /var/log/noobia/aigel
chown -R aria:aria /var/log/noobia/aigel

# ------------------------------------------------------------------
# 4. Launch each script
# ------------------------------------------------------------------
declare -A pids
for script in "$SERVICES_DIR"/*.sh; do
  name=$(basename "$script" .sh)
  echo "Starting $name…"
  if [[ $REALTIME -eq 1 ]]; then
    # Prefix each line with service name for interleaved output
    ($script --interval "$DEFAULT_INTERVAL_MS" --period "$DEFAULT_PERIOD_S" |
     sed "s/^/${name}: /") &
  else
    $script --interval "$DEFAULT_INTERVAL_MS" --period "$DEFAULT_PERIOD_S" &
  fi
  pids["$name"]=$!

done

# ------------------------------------------------------------------
# 5. Optional timeout / wait
# ------------------------------------------------------------------
if [[ $DURATION -gt 0 ]]; then
  echo "Running for $DURATION seconds…"
  sleep "$DURATION"
  echo "Terminating services…"
  for pid in "${pids[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
else
  # Wait for all background jobs to finish
  wait
fi

echo "All diagnostics finished."
