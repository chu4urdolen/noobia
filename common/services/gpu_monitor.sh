#!/usr/bin/env bash
# gpu_monitor.sh — Aigel GPU monitor for Nexus (RTX 5090)
#
# Single-script GPU monitor: samples power, utilization, temperature, VRAM
# and power limit once per second via nvidia-smi, appending rows to an
# hourly CSV in /var/log/noobia_gpu/ (override with AIGEL_GPU_LOG_DIR).
#
# CSV columns:
#   timestamp,power_w,util_pct,temp_c,vram_used_mb,power_limit_w,event
#
# Shutdown handling:
#   * While running, a D-Bus listener watches logind's PrepareForShutdown
#     signal, writes a SHUTDOWN row and exits the monitor.
#   * On startup, if the current hour's CSV already exists and its last row
#     is a SHUTDOWN row, the previous shutdown was graceful and the file is
#     removed.  Otherwise the file is kept as an incident report and new
#     samples are appended to it.
#
# Runs as a systemd service (noobia_gpu_monitor.service).  Designed to be
# the only script and the only unit for GPU monitoring.

set -euo pipefail

LOG_DIR="${AIGEL_GPU_LOG_DIR:-/var/log/noobia_gpu}"
mkdir -p "$LOG_DIR"

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
# Main loop: one sample per second.
# ---------------------------------------------------------------------------
trap 'exit 0' TERM
while :; do
    write_row
    sleep 1
done
