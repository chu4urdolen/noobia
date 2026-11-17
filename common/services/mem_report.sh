#!/usr/bin/env bash
set -euo pipefail

# Default config
CONFIG_FILE="/noobia/aigel/config.json"
INTERVAL_MS=100
PERIOD_S=300

# CLI overrides
while [[ $# -gt 0 ]]; do
  case "$1" in
    --interval) INTERVAL_MS=$2; shift 2;;
    --period)   PERIOD_S=$2;   shift 2;;
    *) shift;;
  esac
done

# Override with config.json if present
if [[ -f "$CONFIG_FILE" ]]; then
  [[ -z ${INTERVAL_MS:+set} ]] && INTERVAL_MS=$(jq -r '.sample_interval_ms' "$CONFIG_FILE")
  [[ -z ${PERIOD_S:+set}   ]] && PERIOD_S=$(jq -r '.sample_period_s' "$CONFIG_FILE")
fi

LOGDIR="/var/log/noobia/aigel"
mkdir -p "$LOGDIR"
LOGFILE="$LOGDIR/mem_report.log"

start_ts=$(date +%s)
end_ts=$((start_ts + PERIOD_S))
first_minute_done=false
minutes_logged=0
last_minute_ts=0
last_hour_ts=0

while (( $(date +%s) < end_ts )); do
  ts=$(date +%s)
  iso_ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  mem=$(free -h | awk 'NR==2{print "Memory: " $3 "/" $2 " used (" $4 " free)"}')
  if command -v nvidia-smi >/dev/null 2>&1; then
    vram=$(nvidia-smi --query-gpu=memory.total,memory.used,memory.free --format=csv,noheader,nounits | awk -F, '{printf "VRAM: %dMiB total, %dMiB used, %dMiB free\n", $1,$2,$3}')
  else
    vram="VRAM: NVIDIA not detected"
  fi
  output="$iso_ts $mem\n$vram"
  log_this=false
  if ! $first_minute_done; then
    log_this=true
    if (( ts - start_ts >= 60 )); then
      first_minute_done=true
    fi
  else
    if (( minutes_logged < 60 )); then
      if (( ts - last_minute_ts >= 60 )); then
        log_this=true
        last_minute_ts=$ts
        minutes_logged=$((minutes_logged + 1))
      fi
    else
      if (( ts - last_hour_ts >= 3600 )); then
        log_this=true
        last_hour_ts=$ts
      fi
    fi
  fi
  if $log_this; then
    echo -e "$output" >> "$LOGFILE"
  fi
  printf "%s\n" "$output"
  sleep "$(awk "BEGIN{printf \"%.3f\", $INTERVAL_MS/1000}")"
done
