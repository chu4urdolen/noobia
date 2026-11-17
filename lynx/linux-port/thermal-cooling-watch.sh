#!/bin/sh
# Modest RAM-only soft throttling. Existing temperature shutdown watchers stay on.
set -eu
base=/run/lynx/thermal-cooling-watch
decide() {
    previous=$1
    value=$2
    case "$previous" in 0|1) ;; *) return 1;; esac
    case "$value" in ''|*[!0-9]*) echo "$previous"; return;; esac
    if [ "$value" -le 0 ] || [ "$value" -gt 125000 ]; then
        echo "$previous"
    elif [ "$value" -ge 45000 ]; then
        echo 1
    elif [ "$value" -le 40000 ]; then
        echo 0
    else
        echo "$previous"
    fi
}
action() {
    desired=$1 actual=$2 owned=$3 blocked=$4
    case "$desired:$owned:$blocked" in *[!01:]*) return 1;; esac
    case "$actual" in ''|*[!0-9]*) echo unavailable; return;; esac
    if [ "$owned" = 1 ] && [ "$actual" != 1 ]; then
        echo cede
    elif [ "$blocked" = 1 ]; then
        echo hold
    elif [ "$owned" = 1 ] && [ "$desired" = 0 ]; then
        echo restore
    elif [ "$owned" = 0 ] && [ "$desired" = 1 ] && [ "$actual" = 0 ]; then
        echo limit
    else
        echo hold
    fi
}
temperature() {
    maximum=0 cpu_count=0 soc_count=0
    for zone in /sys/class/thermal/thermal_zone*; do
        kind=$(cat "$zone/type")
        case "$kind" in
            soc_max) soc_count=$((soc_count + 1));;
            cpu_*) cpu_count=$((cpu_count + 1));;
            *) continue;;
        esac
        value=$(cat "$zone/temp" 2>/dev/null) || return 1
        case "$value" in ''|*[!0-9]*) return 1;; esac
        [ "$value" -gt 0 ] && [ "$value" -le 125000 ] || return 1
        [ "$value" -le "$maximum" ] || maximum=$value
    done
    [ "$soc_count" -ge 1 ] && [ "$cpu_count" -ge 2 ] || return 1
    echo "$maximum"
}
restore() {
    [ -s "$base/devices" ]
    if [ -r "$base/pid" ] && kill -0 "$(cat "$base/pid")" 2>/dev/null; then
        echo 'Stop and verify the owned watcher process before restoring.' >&2
        return 1
    fi
    while read -r dev; do
        case "$dev" in /sys/class/thermal/cooling_device[0-9]*) ;; *) return 1;; esac
        if [ "$(cat "$base/$(basename "$dev").owned")" = 1 ]; then
            actual=$(cat "$dev/cur_state")
            if [ "$actual" = 1 ]; then echo 0 > "$dev/cur_state"; fi
            echo 0 > "$base/$(basename "$dev").owned"
        fi
    done < "$base/devices"
    echo THERMAL_COOLING_OWNED_LIMITS_RELEASED
}
case "${1:-}" in
    --decide) [ "$#" = 3 ]; decide "$2" "$3"; exit;;
    --action) [ "$#" = 5 ]; action "$2" "$3" "$4" "$5"; exit;;
    --restore) restore; exit;;
    --run) ;;
    *) echo 'Usage: thermal-cooling-watch.sh --run|--restore' >&2; exit 2;;
esac
for pidfile in /run/lynx/thermal-watch.pid /run/lynx/battery-watch.pid; do
    kill -0 "$(cat "$pidfile")"
done
initial=$(temperature)
[ "$initial" -lt 40000 ]
mkdir "$base"  # Never overwrite ownership or run a second instance.
count=0
for dev in /sys/class/thermal/cooling_device*; do
    kind=$(cat "$dev/type")
    case "$kind" in thermal-cpufreq-[0-2]) ;; *) continue;; esac
    [ "$(cat "$dev/cur_state")" = 0 ]
    [ "$(cat "$dev/max_state")" -ge 1 ]
    echo "$dev" >> "$base/devices"
    echo 0 > "$base/$(basename "$dev").owned"
    echo 0 > "$base/$(basename "$dev").blocked"
    count=$((count + 1))
done
[ "$count" = 3 ]
echo "$$" > "$base/pid"
echo THERMAL_COOLING_READY
echo ready > "$base/ready"
desired=0
while :; do
    if value=$(temperature); then
        desired=$(decide "$desired" "$value")
        echo "THERMAL_COOLING_SAMPLE temperature=$value desired=$desired"
        while read -r dev; do
            stem=$base/$(basename "$dev")
            actual=$(cat "$dev/cur_state")
            operation=$(action "$desired" "$actual" "$(cat "$stem.owned")" "$(cat "$stem.blocked")")
            case "$operation" in
                limit)
                    echo 1 > "$dev/cur_state"
                    [ "$(cat "$dev/cur_state")" = 1 ]
                    echo 1 > "$stem.owned"
                    echo "THERMAL_COOLING_LIMIT $dev";;
                restore)
                    echo 0 > "$dev/cur_state"
                    echo 0 > "$stem.owned"
                    echo "THERMAL_COOLING_RELEASE $dev";;
                cede)
                    echo 0 > "$stem.owned"
                    echo 1 > "$stem.blocked"
                    echo "THERMAL_COOLING_CEDE $dev actual=$actual";;
                unavailable) echo "THERMAL_COOLING_STATE_UNAVAILABLE $dev";;
                hold) ;;
                *) exit 1;;
            esac
        done < "$base/devices"
    else
        echo THERMAL_COOLING_SENSOR_UNAVAILABLE_HOLD
    fi
    sleep 5
done
