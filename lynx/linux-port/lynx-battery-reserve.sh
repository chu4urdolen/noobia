#!/bin/sh
# Preserve a battery reserve during unplugged Alpine operation.
# The existing independent health supervisor handles hot or missing sensors.
set -eu
BB=/bin/busybox
SOURCE=/sys/bus/i2c/devices/7-0055/battery_snapshot
STATE=/run/lynx/battery-reserve
CUTOFF=20
INTERVAL=30

read_capacity() {
    sample=$($BB cat "$SOURCE") || return 1
    identity=$(printf '%s\n' "$sample" | $BB sed -n 's/^gauge_device_type=//p')
    error=$(printf '%s\n' "$sample" | $BB sed -n 's/^capacity_error=//p')
    capacity=$(printf '%s\n' "$sample" | $BB sed -n 's/^capacity_percent=//p')
    [ "$identity" = 42495 ] && [ "$error" = 0 ] || return 1
    case "$capacity" in ''|*[!0-9]*) return 1 ;; esac
    [ "$capacity" -le 100 ] || return 1
    printf '%s\n' "$capacity"
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
        capacity=$(read_capacity) || exit 1
        printf 'LYNX_BATTERY_RESERVE capacity_percent=%s cutoff_percent=%s\n' "$capacity" "$CUTOFF"
        ;;
    --watch)
        [ -d /run/lynx ] || exit 1
        $BB mkdir "$STATE" || exit 1
        printf '%s\n' "$$" > "$STATE/pid"
        low=0
        failed=0
        while :; do
            if capacity=$(read_capacity); then
                failed=0
                if [ "$capacity" -le "$CUTOFF" ]; then
                    low=$((low+1))
                    printf 'LYNX_BATTERY_RESERVE_LOW capacity_percent=%s consecutive=%s\n' "$capacity" "$low"
                    if [ "$low" -ge 3 ]; then
                        request_shutdown low_capacity
                        exit 2
                    fi
                else
                    low=0
                fi
            else
                low=0
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
