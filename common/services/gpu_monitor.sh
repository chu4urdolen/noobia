#!/usr/bin/env bash
# gpu_monitor.sh — Aigel GPU monitor for Nexus (RTX 5090)
#
# Single-script GPU monitor: samples power, utilization, temperature, VRAM
# and power limit via nvidia-smi on the unified Aigel sampling schedule,
# appending CSV rows to an hourly file in $LOG_DIR (default
# /var/log/noobia_gpu, override with AIGEL_GPU_LOG_DIR).
#
# CSV columns:
#   timestamp,power_w,util_pct,temp_c,vram_used_mb,power_limit_w,event
#
# Power limit:
#   * At startup the service sets the GPU power limit to 500 W by default
#     (the RTX 5090 default is 575 W and the setting does not survive reboots).
#     Override with AIGEL_GPU_POWER_LIMIT_W or "power_limit_w" in the policy
#     file.  Never aborts startup if the GPU/driver is unavailable.
#
# Shutdown handling:
#   * While running, a D-Bus listener watches logind's PrepareForShutdown
#     signal, writes a SHUTDOWN row and exits the monitor.
#   * On startup, if the current hour's CSV already exists and its last row
#     is a SHUTDOWN row, the previous shutdown was graceful and the file is
#     removed.  Otherwise the file is kept as an incident report and new
#     samples are appended to it.
#
# Runs as a systemd service (gpu_monitor.service) until the next service
# restart (boot).  Designed to be the only script and the only unit for
# GPU monitoring.

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

# GPU store directory (separate from the text-report services).
LOG_DIR="${AIGEL_GPU_LOG_DIR:-/var/log/noobia_gpu}"
mkdir -p "$LOG_DIR"

# now_mono_ms -> current monotonic time in ms (boot-based, from /proc/uptime).
# Used for ALL interval/phase timing so NTP steps on the wall clock (which can
# make `date` jump backwards) never corrupt the sampling cadence.  The stored
# timestamp label still uses the wall clock (`date -u`) for human/log use.
now_mono_ms() {
    local up whole frac
    read -r up _ < /proc/uptime
    whole=${up%%.*}; frac=${up#*.}
    printf '%d' $(( 10#$whole * 1000 + 10#$frac * 10 ))
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

hour_file() {
    printf '%s/%s.csv' "$LOG_DIR" "$(date -u +%Y-%m-%d_%H)"
}

# Print "power_w util_pct temp_c vram_used_mb power_limit_w" (all fields
# empty if nvidia-smi is unavailable or the GPU query fails).
gpu_fields() {
    nvidia-smi --query-gpu=power.draw,utilization.gpu,temperature.gpu,memory.used,power.limit \
               --format=csv,noheader,nounits 2>/dev/null |
    awk -F', *' 'NR==1{printf "%s %s %s %s %s", $1, $2, $3, $4, $5}'
}

# Append one CSV row.  $1 is the event name (empty for regular samples).
write_row() {
    local event="${1:-}"
    local power="" util="" temp="" vram="" limit=""
    read -r power util temp vram limit < <(gpu_fields) || true
    printf '%s,%s,%s,%s,%s,%s,%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)" \
        "${power}" "${util}" "${temp}" "${vram}" "${limit}" "${event}" >> "$(hour_file)"
}

# ---------------------------------------------------------------------------
# Startup: resolve the current hour's file, applying the shutdown rule.
# ---------------------------------------------------------------------------
FILE="$(hour_file)"
if [[ -f "$FILE" ]]; then
    last_event="$(awk 'END{print}' "$FILE" | awk -F',' '{print $NF}')"
    if [[ "$last_event" == "SHUTDOWN" ]]; then
        rm -f "$FILE"     # previous shutdown was graceful – drop the file
    fi
fi
if [[ ! -s "$FILE" ]]; then
    printf 'timestamp,power_w,util_pct,temp_c,vram_used_mb,power_limit_w,event\n' > "$FILE"
fi

# ---------------------------------------------------------------------------
# Startup: enforce the GPU power budget.
#
# The RTX 5090 ships with a 575 W default limit (allowed 400-600 W) and the
# limit does not survive reboots, so the service pins it on every start.
# Precedence: AIGEL_GPU_POWER_LIMIT_W > "power_limit_w" in the policy file
#             > built-in default (500 W).
# ---------------------------------------------------------------------------
GPU_POWER_LIMIT_W="${AIGEL_GPU_POWER_LIMIT_W:-}"
if [[ -z "$GPU_POWER_LIMIT_W" ]] && command -v jq >/dev/null 2>&1 && [[ -f "$CONFIG_FILE" ]]; then
    GPU_POWER_LIMIT_W="$(jq -r '.power_limit_w // empty' "$CONFIG_FILE" 2>/dev/null || true)"
fi
GPU_POWER_LIMIT_W="${GPU_POWER_LIMIT_W:-500}"

set_power_limit() {
    local attempt=0
    if ! command -v nvidia-smi >/dev/null 2>&1; then
        echo "warn: nvidia-smi not found; GPU power limit not set" >&2
        return 0
    fi
    while (( attempt < 10 )); do
        if nvidia-smi -L >/dev/null 2>&1; then
            if nvidia-smi -pl "$GPU_POWER_LIMIT_W" >/dev/null 2>&1; then
                echo "gpu power limit set to ${GPU_POWER_LIMIT_W} W" >&2
            else
                echo "warn: nvidia-smi -pl ${GPU_POWER_LIMIT_W} failed" >&2
            fi
            return 0
        fi
        attempt=$(( attempt + 1 ))
        sleep 1
    done
    echo "warn: GPU not ready after 10 s; power limit not set" >&2
    return 0
}

set_power_limit

# ---------------------------------------------------------------------------
# D-Bus listener: record SHUTDOWN and stop the monitor on PrepareForShutdown.
# ($$ inside the subshell is still the main script's PID.)
# ---------------------------------------------------------------------------
if command -v dbus-monitor >/dev/null 2>&1; then
    (
        dbus-monitor --system \
            "type='signal',interface='org.freedesktop.login1.Manager',member='PrepareForShutdown'" \
            2>/dev/null |
        while IFS= read -r line; do
            case "$line" in
                *PrepareForShutdown*)
                    write_row SHUTDOWN
                    kill "$$" 2>/dev/null || true
                    exit 0
                    ;;
            esac
        done
    ) &
fi

# ---------------------------------------------------------------------------
# Main loop: sample on the unified phase schedule until the service restarts.
# ---------------------------------------------------------------------------
start_ms=$(now_mono_ms)
last_ms=0
trap 'exit 0' TERM INT
while :; do
    now_ms=$(now_mono_ms)
    due=$(due_ms_for $(( now_ms - start_ms )))
    if (( last_ms == 0 )) || (( now_ms - last_ms >= due )); then
        write_row
        last_ms=$(now_mono_ms)
    fi
    sleep 0.1
done
