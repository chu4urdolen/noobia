#!/bin/busybox sh
# Continuous CPU/SoC observations; no elapsed-time shutdown.
# Battery sensing is added separately after identification. Missing/invalid
# readings are logged, never interpreted as cool or as a valid safety proof.
BB=/bin/busybox
# Tom 2026-11-22: never act on one glitchy reading; 10 in a row (50 s at 5 s).
READS_TO_ACT=10
over=0
GUARD_SWITCH=/etc/lynx/power-thermal-guard.disable
THERMAL_ROOT=/sys/class/thermal
READY=/run/lynx/thermal-watch.ready
STOP_MILLIDEGREES=75000

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
    if [ ! -e "$READY" ]; then
        echo THERMAL_WATCH_WAITING_FOR_SENSORS
        return 0
    fi
    count=0
    maximum=0
    hot=0
    for p in "$THERMAL_ROOT"/thermal_zone*; do
        [ -r "$p/type" ] || continue
        IFS= read -r kind < "$p/type" || continue
        case "$kind" in soc_max|cpu_*) ;; *) continue ;; esac
        if ! IFS= read -r value < "$p/temp"; then
            echo "THERMAL_WATCH_UNREADABLE $kind"
            continue
        fi
        case "$value" in ''|*[!0-9]*) echo "THERMAL_WATCH_INVALID $kind"; continue ;; esac
        if [ "$value" -le 0 ]; then
            echo "THERMAL_WATCH_INVALID $kind"
            continue
        fi
        count=$((count + 1))
        [ "$value" -le "$maximum" ] || maximum=$value
        [ "$value" -lt "$STOP_MILLIDEGREES" ] || hot=1
    done
    echo "THERMAL_WATCH_SAMPLE valid=$count maximum_millidegrees=$maximum"
    if [ "$hot" = 1 ]; then over=$((over+1)); else over=0; fi
    if [ "$hot" = 1 ] && [ "$over" -ge "$READS_TO_ACT" ]; then
        rest_lynx "too warm ($((maximum / 1000)) C)"
        over=0
    elif [ "$hot" = 1 ]; then
        echo "THERMAL_WATCH_OVER_LIMIT consecutive=$over of $READS_TO_ACT (no action yet)"
    fi
    [ "$count" -gt 0 ] || echo THERMAL_WATCH_NO_VALID_CPU_READINGS
    return 0
}

case "$1" in
    --once) check_once; exit $? ;;
esac
while :; do
    check_once || exit $?
    "$BB" sleep 5
done
