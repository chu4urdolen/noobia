#!/bin/sh
# Preserve a reserve while allowing verified net charging at low capacity.
# The independent health supervisor still protects missing and hot sensors.
set -eu
BB=/bin/busybox
SOURCE=/sys/bus/i2c/devices/7-0055/battery_snapshot
STATE=/run/lynx/battery-reserve
CUTOFF=20
INTERVAL=30
CHARGE_CURRENT_MIN=50
CHARGE_TEMP_MAX=40000
CRITICAL_CUTOFF=10
MAX_HOLD_SAMPLES=240

read_battery() {
    sample=$($BB cat "$SOURCE") || return 1
    identity=$(printf '%s\n' "$sample" | $BB sed -n 's/^gauge_device_type=//p')
    capacity_error=$(printf '%s\n' "$sample" | $BB sed -n 's/^capacity_error=//p')
    current_error=$(printf '%s\n' "$sample" | $BB sed -n 's/^current_error=//p')
    temperature_error=$(printf '%s\n' "$sample" | $BB sed -n 's/^temperature_error=//p')
    capacity=$(printf '%s\n' "$sample" | $BB sed -n 's/^capacity_percent=//p')
    current=$(printf '%s\n' "$sample" | $BB sed -n 's/^gauge_current_ma_signed=//p')
    temperature=$(printf '%s\n' "$sample" | $BB sed -n 's/^temperature_millidegrees_celsius=//p')
    [ "$identity" = 42495 ] && [ "$capacity_error" = 0 ] &&
        [ "$current_error" = 0 ] && [ "$temperature_error" = 0 ] || return 1
    case "$capacity" in ''|*[!0-9]*) return 1 ;; esac
    [ "$capacity" -le 100 ] || return 1
    case "$current" in
        -*) digits=${current#-} ;;
        *) digits=$current ;;
    esac
    case "$digits" in ''|*[!0-9]*) return 1 ;; esac
    [ "$current" -ge -32768 ] && [ "$current" -le 32767 ] || return 1
    case "$temperature" in ''|*[!0-9]*) return 1 ;; esac
    [ "$temperature" -le 60000 ] || return 1
    printf '%s %s %s\n' "$capacity" "$current" "$temperature"
}

request_shutdown() {
    reason=$1
    printf 'LYNX_BATTERY_RESERVE_SHUTDOWN reason=%s\n' "$reason"
    printf '<2>LYNX_BATTERY_RESERVE_SHUTDOWN reason=%s\n' "$reason" > /dev/kmsg || true
    /sbin/openrc-shutdown --poweroff now || true
    $BB sleep 15
    $BB poweroff -f
}

case "${1:-}" in
    --once)
        sample=$(read_battery) || exit 1
        set -- $sample
        printf 'LYNX_BATTERY_RESERVE capacity_percent=%s cutoff_percent=%s current_ma=%s temperature_millidegrees=%s\n' \
            "$1" "$CUTOFF" "$2" "$3"
        ;;
    --watch)
        [ -d /run/lynx ] || exit 1
        $BB mkdir "$STATE" || exit 1
        printf '%s\n' "$$" > "$STATE/pid"
        low=0
        failed=0
        charging=0
        hold=0
        while :; do
            if sample=$(read_battery); then
                failed=0
                set -- $sample
                capacity=$1 current=$2 temperature=$3
                if [ "$temperature" -ge "$CHARGE_TEMP_MAX" ]; then
                    request_shutdown charging_temperature
                    exit 2
                fi
                if [ "$capacity" -le "$CRITICAL_CUTOFF" ]; then
                    request_shutdown critical_capacity
                    exit 2
                fi
                if [ "$capacity" -gt "$CUTOFF" ]; then
                    low=0 charging=0 hold=0
                elif [ "$current" -ge "$CHARGE_CURRENT_MIN" ]; then
                    charging=$((charging+1))
                    if [ "$charging" -ge 2 ]; then
                        low=0
                        hold=$((hold+1))
                        printf 'LYNX_BATTERY_RESERVE_CHARGING capacity_percent=%s current_ma=%s hold_samples=%s\n' \
                            "$capacity" "$current" "$hold"
                        if [ "$hold" -ge "$MAX_HOLD_SAMPLES" ]; then
                            request_shutdown no_charge_progress
                            exit 2
                        fi
                    fi
                else
                    charging=0
                    low=$((low+1))
                    printf 'LYNX_BATTERY_RESERVE_LOW capacity_percent=%s current_ma=%s consecutive=%s\n' \
                        "$capacity" "$current" "$low"
                    if [ "$low" -ge 3 ]; then
                        request_shutdown low_capacity
                        exit 2
                    fi
                fi
            else
                charging=0
                failed=$((failed+1))
                printf 'LYNX_BATTERY_RESERVE_GAUGE_FAILED consecutive=%s\n' "$failed"
                if [ "$failed" -ge 3 ]; then
                    request_shutdown gauge_unavailable
                    exit 2
                fi
            fi
            $BB sleep "$INTERVAL"
        done
        ;;
    *) echo 'Usage: lynx-battery-reserve.sh --once|--watch' >&2; exit 2 ;;
esac
