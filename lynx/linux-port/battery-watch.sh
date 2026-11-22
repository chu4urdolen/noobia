#!/bin/busybox sh
# Read the fixed read-only sysfs snapshot every five seconds. No timed stop.
BB=/bin/busybox
# Tom 2026-11-22: never act on one glitchy reading; 10 in a row (50 s at 5 s).
READS_TO_ACT=10
over=0
GUARD_SWITCH=/etc/lynx/power-thermal-guard.disable
SOURCE=/sys/bus/i2c/devices/7-0055/battery_snapshot
LAST=/run/lynx/battery-last
STOP_MILLIDEGREES=50000

check_once() {
    IFS=' ' read -r uptime rest < /proc/uptime
    printf 'sample_uptime_seconds=%s\n' "$uptime" > "$LAST.tmp"
    if ! "$BB" cat "$SOURCE" >> "$LAST.tmp"; then
        echo read_error=1 >> "$LAST.tmp"
        "$BB" mv "$LAST.tmp" "$LAST"
        echo BATTERY_WATCH_READ_FAILED
        return 1
    fi
    "$BB" mv "$LAST.tmp" "$LAST"
    temperature=
    temp_error=
    while IFS='=' read -r key value; do
        case "$key" in
            temperature_millidegrees_celsius) temperature=$value ;;
            temperature_error) temp_error=$value ;;
        esac
    done < "$LAST"
    digits=${temperature#-}
    case "$digits" in ''|*[!0-9]*) echo BATTERY_WATCH_INVALID_TEMPERATURE; return 1 ;; esac
    [ "$temp_error" = 0 ] || { echo BATTERY_WATCH_TEMPERATURE_UNAVAILABLE; return 1; }
    echo "BATTERY_WATCH_SAMPLE uptime=$uptime temperature_millidegrees=$temperature"
    # Guard switch: keep sampling (lynx-health reads the sample), never act.
    [ -e "$GUARD_SWITCH" ] && { over=0; return 0; }
    if [ "$temperature" -ge "$STOP_MILLIDEGREES" ]; then over=$((over+1)); else over=0; fi
    if [ "$temperature" -ge "$STOP_MILLIDEGREES" ] && [ "$over" -lt "$READS_TO_ACT" ]; then
        echo "BATTERY_WATCH_OVER_LIMIT consecutive=$over of $READS_TO_ACT (no action yet)"
        return 0
    fi
    if [ "$temperature" -ge "$STOP_MILLIDEGREES" ]; then
        echo "BATTERY_WATCH_TEMPERATURE_HIGH cutoff_millidegrees=$STOP_MILLIDEGREES; throttling to low power"
        for dev in /sys/class/thermal/cooling_device*; do
            [ -f "$dev/cur_state" ] && echo 1 > "$dev/cur_state" 2>/dev/null || true
        done
        return 0
    fi
    return 0
}
case "$1" in --once) check_once; exit $? ;; esac
while :; do
    check_once
    [ "$?" -ne 2 ] || exit 2
    "$BB" sleep 5
done
