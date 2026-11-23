#!/bin/busybox sh
# Read the fixed read-only sysfs snapshot every five seconds. No timed stop.
BB=/bin/busybox
# Tom 2026-11-22: never act on one glitchy reading; 10 in a row (50 s at 5 s).
READS_TO_ACT=10
over=0
low=0
LOW_PERCENT=10
GUARD_SWITCH=/etc/lynx/power-thermal-guard.disable
SOURCE=/sys/bus/i2c/devices/7-0055/battery_snapshot
LAST=/run/lynx/battery-last
STOP_MILLIDEGREES=50000

# Tom 2026-11-23: a guard never shuts Lynx down - it sends her to power
# saving (the START screen) with the reason, once per 10-reading run.
rest_lynx() {
    case "$(cat /var/lib/noobia/power-mode 2>/dev/null)" in saving*) return 0;; esac
    echo "GUARD_POWER_SAVING $1"
    [ -x /usr/local/bin/lynx-power-mode ] && /usr/local/bin/lynx-power-mode saving "$1" >/dev/null 2>&1 &
    if [ ! -e "$GUARD_SWITCH" ]; then
        for dev in /sys/class/thermal/cooling_device*; do
            [ -f "$dev/cur_state" ] && echo 1 > "$dev/cur_state" 2>/dev/null || true
        done
    fi
    return 0
}

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
    capacity=
    current=
    while IFS='=' read -r key value; do
        case "$key" in
            temperature_millidegrees_celsius) temperature=$value ;;
            temperature_error) temp_error=$value ;;
            capacity_percent) capacity=$value ;;
            gauge_current_ma_signed) current=$value ;;
        esac
    done < "$LAST"
    digits=${temperature#-}
    case "$digits" in ''|*[!0-9]*) echo BATTERY_WATCH_INVALID_TEMPERATURE; return 1 ;; esac
    [ "$temp_error" = 0 ] || { echo BATTERY_WATCH_TEMPERATURE_UNAVAILABLE; return 1; }
    echo "BATTERY_WATCH_SAMPLE uptime=$uptime temperature_millidegrees=$temperature"
    if [ "$temperature" -ge "$STOP_MILLIDEGREES" ]; then over=$((over+1)); else over=0; fi
    if [ "$over" -ge "$READS_TO_ACT" ]; then
        rest_lynx "battery too warm ($((temperature / 1000)) C)"
        over=0
    elif [ "$over" -gt 0 ]; then
        echo "BATTERY_WATCH_OVER_LIMIT consecutive=$over of $READS_TO_ACT (no action yet)"
    fi
    # Low battery while not charging -> rest (10 readings in a row).
    case "$capacity:$current" in
        *[!0-9:-]*|:*|*:) low=0 ;;
        *) if [ "$capacity" -le "$LOW_PERCENT" ] && [ "$current" -le 0 ]; then low=$((low+1)); else low=0; fi ;;
    esac
    if [ "$low" -ge "$READS_TO_ACT" ]; then
        rest_lynx "battery low ($capacity%)"
        low=0
    fi
    return 0
}
case "$1" in --once) check_once; exit $? ;; esac
while :; do
    check_once
    [ "$?" -ne 2 ] || exit 2
    "$BB" sleep 5
done
