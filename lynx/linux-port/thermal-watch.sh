#!/bin/busybox sh
# Continuous CPU/SoC observations; no elapsed-time shutdown.
# Battery sensing is added separately after identification. Missing/invalid
# readings are logged, never interpreted as cool or as a valid safety proof.
BB=/bin/busybox
THERMAL_ROOT=/sys/class/thermal
READY=/run/lynx/thermal-watch.ready
STOP_MILLIDEGREES=75000

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
    if [ "$hot" = 1 ]; then
        echo "THERMAL_WATCH_TEMPERATURE_HIGH cutoff_millidegrees=$STOP_MILLIDEGREES; throttling to low power"
        for dev in "$THERMAL_ROOT"/cooling_device*; do
            [ -f "$dev/cur_state" ] && echo 1 > "$dev/cur_state" 2>/dev/null || true
        done
        return 0
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
