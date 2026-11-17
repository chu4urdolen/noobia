#!/usr/bin/env bash
# cpu_report.sh — Aigel CPU health service
#
# Samples per-core CPU utilization (two snapshots 1 s apart) plus a top
# summary, on the unified Aigel sampling schedule.  Every sample is
# appended to the background store $LOG_DIR/cpu_report.log.

set -euo pipefail

# ======================= unified sampling engine ==========================
#
# All Aigel health services share this sampling schedule.  Each service
# runs until the next service restart (boot) and appends every sample to
# its background store:
#
#   Phase 1 (hot):    sample every INTERVAL_MS  for the first PERIOD_S
#   Phase 2 (medium): sample every 60 s         until 1 h after start
#   Phase 3 (hourly): sample every 1 h          until the service restarts
#
# Arguments:   --interval <ms>   hot-phase sample interval (default 1000)
#             --period <s>      hot-phase duration        (default 300)
# Precedence:  CLI arguments > $AIGEL_CONFIG > built-in defaults
# Environment: AIGEL_CONFIG  policy file (jq: sample_interval_ms, sample_period_s)
#             AIGEL_LOG_DIR  background store dir (default /var/log/noobia/aigel)
#             AIGEL_MED_MS / AIGEL_HOUR_MS / AIGEL_HOURDUE_MS  (test knobs;
#             defaults 60000 / 3600000 / 3600000 ms)
#
CONFIG_FILE="${AIGEL_CONFIG:-/noobia/aigel/config.json}"
LOG_DIR="${AIGEL_LOG_DIR:-/var/log/noobia/aigel}"

INTERVAL_MS=1000
PERIOD_S=300
MED_MS="${AIGEL_MED_MS:-60000}"
HOUR_MS="${AIGEL_HOUR_MS:-3600000}"
HOURDUE_MS="${AIGEL_HOURDUE_MS:-3600000}"

if command -v jq >/dev/null 2>&1 && [[ -f "$CONFIG_FILE" ]]; then
    cfg_v=$(jq -r '.sample_interval_ms // empty' "$CONFIG_FILE" 2>/dev/null || true)
    [[ -n "$cfg_v" ]] && INTERVAL_MS="$cfg_v"
    cfg_v=$(jq -r '.sample_period_s // empty' "$CONFIG_FILE" 2>/dev/null || true)
    [[ -n "$cfg_v" ]] && PERIOD_S="$cfg_v"
fi

while [[ $# -gt 0 ]]; do
    case "$1" in
        --interval) INTERVAL_MS="${2:?--interval needs a value}"; shift 2 ;;
        --period)   PERIOD_S="${2:?--period needs a value}"; shift 2 ;;
        *)          echo "warning: ignoring unknown argument: $1" >&2; shift ;;
    esac
done

mkdir -p "$LOG_DIR"

# now_mono_ms -> current monotonic time in ms (boot-based, from /proc/uptime).
# Used for ALL interval/phase timing so NTP steps on the wall clock (which can
# make `date` jump backwards) never corrupt the sampling cadence.  The stored
# timestamp label still uses the wall clock (`date -u`) for human/log use.
now_mono_ms() {
    local up whole frac
    read -r up _ < /proc/uptime
    whole=${up%%.*}; frac=${up#*.}
    printf '%d' $(( whole * 1000 + frac * 10 ))
}

# due_ms_for <elapsed_ms> -> prints the current phase's sample interval (ms)
due_ms_for() {
    local e=$1
    if (( e < PERIOD_S * 1000 )); then
        printf '%s' "$INTERVAL_MS"
    elif (( e < HOUR_MS )); then
        printf '%s' "$MED_MS"
    else
        printf '%s' "$HOURDUE_MS"
    fi
}
# ==========================================================================

STORE_FILE="$LOG_DIR/cpu_report.log"

take_sample() {
    local snap1 snap2 line1 line2 cpu_name usage=""
    local -a f1 f2
    snap1=$(grep '^cpu[0-9]' /proc/stat)
    sleep 1
    snap2=$(grep '^cpu[0-9]' /proc/stat)
    while IFS= read -r line1; do
        cpu_name=${line1%% *}
        line2=$(grep "^${cpu_name} " <<< "$snap2" || true)
        read -ra f1 <<< "$line1"
        read -ra f2 <<< "$line2"
        local idle1=${f1[4]:-0} idle2=${f2[4]:-0} total1=0 total2=0 i u=0
        for i in 1 2 3 4 5 6 7 8; do
            total1=$(( total1 + ${f1[i]:-0} ))
            total2=$(( total2 + ${f2[i]:-0} ))
        done
        local dt=$(( total2 - total1 )) di=$(( idle2 - idle1 ))
        if (( dt > 0 )); then
            u=$(( (1000 * (dt - di) / dt + 5) / 10 ))
        fi
        usage+="${cpu_name}=${u}% "
    done <<< "$snap1"
    local top
    top=$(top -bn1 2>/dev/null | head -n 4 | tr '\n' ' ' | tr -s ' ' | tr -d '\r')
    printf 'cores: %s | top: %s' "${usage% }" "${top% }"
}

# Run the unified engine until the service is restarted: sample on the
# phase schedule, append each sample to the store, and echo it to the journal.
run_engine() {
    local start_ms last_ms now_ms due line ts
    start_ms=$(now_mono_ms)
    last_ms=0
    trap 'exit 0' TERM INT
    while :; do
        now_ms=$(now_mono_ms)
        due=$(due_ms_for $(( now_ms - start_ms )))
        if (( last_ms == 0 )) || (( now_ms - last_ms >= due )); then
            if line=$(take_sample 2>/dev/null); then
                ts=$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)
                printf '%s %s\n' "$ts" "$line" >> "$STORE_FILE"
                printf '%s %s\n' "$ts" "$line"
            fi
            last_ms=$(now_mono_ms)
        fi
        sleep 0.1
    done
}

run_engine
