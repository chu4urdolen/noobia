#!/bin/sh
# Read-only ZY0603 gauge history. Safety actions belong to lynx-health/reserve.
set -u
SOURCE=/sys/bus/i2c/devices/7-0055/battery_snapshot
LOG_DIR=/var/log/lynx
LOG=$LOG_DIR/power.csv
MAX_BYTES=262144
INTERVAL=60
umask 077

field() {
    printf '%s\n' "$sample" | /bin/busybox sed -n "s/^$1=//p"
}

sample_line() {
    sample=$(/bin/busybox cat "$SOURCE") || return 1
    [ "$(field gauge_device_type)" = 42495 ] || return 1
    for error in capacity_error current_error temperature_error voltage_error; do
        [ "$(field "$error")" = 0 ] || return 1
    done
    capacity=$(field capacity_percent)
    current=$(field gauge_current_ma_signed)
    battery_temp=$(field temperature_millidegrees_celsius)
    voltage=$(field pack_voltage_mv)
    for number in "$capacity" "$battery_temp" "$voltage"; do
        case "$number" in ''|*[!0-9]*) return 1 ;; esac
    done
    case "$current" in
        -*) current_digits=${current#-} ;;
        *) current_digits=$current ;;
    esac
    case "$current_digits" in ''|*[!0-9]*) return 1 ;; esac
    [ "$capacity" -le 100 ] && [ "$battery_temp" -le 60000 ] &&
        [ "$voltage" -ge 5000 ] && [ "$voltage" -le 10000 ] &&
        [ "$current" -ge -32768 ] && [ "$current" -le 32767 ] || return 1
    boot_id=$(/bin/busybox cat /proc/sys/kernel/random/boot_id) || return 1
    case "$boot_id" in *[!0-9a-f-]*|'') return 1 ;; esac
    read -r uptime _ < /proc/uptime || return 1
    uptime=${uptime%%.*}
    case "$uptime" in ''|*[!0-9]*) return 1 ;; esac
    epoch=$(date -u +%s) || return 1
    case "$epoch" in ''|*[!0-9]*) return 1 ;; esac
    printf '%s,%s,%s,%s,%s,%s,%s\n' "$boot_id" "$uptime" "$epoch" \
        "$capacity" "$current" "$battery_temp" "$voltage"
}

rotate() {
    [ -e "$LOG" ] || return 0
    bytes=$(stat -c %s "$LOG") || return 1
    [ "$bytes" -lt "$MAX_BYTES" ] && return 0
    /bin/busybox mv -f "$LOG.2" "$LOG.3" 2>/dev/null || true
    /bin/busybox mv -f "$LOG.1" "$LOG.2" 2>/dev/null || true
    /bin/busybox mv -f "$LOG" "$LOG.1" || return 1
}

record() {
    line=$(sample_line) || {
        /bin/busybox logger -p daemon.err -t lynx-power-history 'LYNX_POWER_HISTORY_GAUGE_FAILED'
        return 1
    }
    /bin/busybox mkdir -p "$LOG_DIR" || return 1
    chmod 0700 "$LOG_DIR" || return 1
    rotate || return 1
    [ -e "$LOG" ] || printf 'boot_id,uptime_s,epoch_s,capacity_percent,current_ma,battery_temp_mC,pack_voltage_mV\n' > "$LOG" || return 1
    printf '%s\n' "$line" >> "$LOG" || return 1
    chmod 0600 "$LOG" || return 1
    /bin/busybox sync "$LOG" || return 1
    printf '%s\n' "$line"
}

case "${1:-}" in
    --once) record ;;
    --watch)
        while :; do
            record || true
            /bin/busybox sleep "$INTERVAL"
        done
        ;;
    *) printf 'Usage: lynx-power-history.sh --once|--watch\n' >&2; exit 2 ;;
esac
