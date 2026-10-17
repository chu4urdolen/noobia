#!/bin/sh
# RAM-only backstop for the three existing on-device power watchers.
# --once is read-only. --watch requests power-off after three consecutive
# invalid observations; the cooling watcher separately applies CPU limits.
set -eu
BB=/bin/busybox
RUN=/run/lynx
PROC=/proc
THERMAL=/sys/class/thermal
STATE=$RUN/health-supervisor

fail() { echo "LYNX_HEALTH_REFUSED $*" >&2; return 1; }

require_process() {
    pidfile=$1 expected=$2
    [ -r "$pidfile" ] || { fail "missing $pidfile"; return 1; }
    pid=$(cat "$pidfile") || return 1
    case "$pid" in ''|*[!0-9]*) fail "invalid pid $pidfile"; return 1;; esac
    kill -0 "$pid" 2>/dev/null || { fail "dead $expected"; return 1; }
    tr '\000' '\n' < "$PROC/$pid/cmdline" | grep -Fxq "$expected" || {
        fail "unexpected process $expected"; return 1;
    }
}

health_once() {
    require_process "$RUN/thermal-watch.pid" /run/lynx/thermal-watch.sh || return 1
    require_process "$RUN/battery-watch.pid" /run/lynx/battery-watch.sh || return 1
    require_process "$RUN/thermal-cooling-watch/pid" /run/lynx/thermal-cooling-watch.sh || return 1
    [ -r "$RUN/battery-last" ] || { fail 'battery snapshot absent'; return 1; }
    [ -r /sys/bus/i2c/devices/7-0055/battery_snapshot ] || { fail 'gauge absent'; return 1; }
    for field in temperature_error voltage_error current_error capacity_error; do
        grep -Fxq "$field=0" "$RUN/battery-last" || { fail "battery $field"; return 1; }
    done
    grep -Fxq 'gauge_device_type=42495' "$RUN/battery-last" || { fail 'gauge identity'; return 1; }
    now=$(cut -d. -f1 "$PROC/uptime") || return 1
    sampled=$(sed -n 's/^sample_uptime_seconds=//p' "$RUN/battery-last") || return 1
    sampled=${sampled%%.*}
    battery=$(sed -n 's/^temperature_millidegrees_celsius=//p' "$RUN/battery-last") || return 1
    capacity=$(sed -n 's/^capacity_percent=//p' "$RUN/battery-last") || return 1
    for number in "$now" "$sampled" "$battery" "$capacity"; do
        case "$number" in ''|*[!0-9]*) fail 'invalid battery numbers'; return 1;; esac
    done
    [ "$now" -ge "$sampled" ] && [ "$((now-sampled))" -le 15 ] || { fail 'stale battery sample'; return 1; }
    [ "$battery" -gt 0 ] && [ "$battery" -lt 45000 ] || { fail 'battery too hot or invalid'; return 1; }
    [ "$capacity" -ge 5 ] && [ "$capacity" -le 100 ] || { fail 'battery charge critical or invalid'; return 1; }

    cpu=0 soc=0 maximum=0
    for zone in "$THERMAL"/thermal_zone*; do
        [ -r "$zone/type" ] && [ -r "$zone/temp" ] || continue
        kind=$(cat "$zone/type") || return 1
        case "$kind" in soc_max) soc=$((soc+1));; cpu_*) cpu=$((cpu+1));; *) continue;; esac
        value=$(cat "$zone/temp") || return 1
        case "$value" in ''|*[!0-9]*) fail "invalid $kind"; return 1;; esac
        [ "$value" -gt 0 ] && [ "$value" -lt 60000 ] || { fail "hot or invalid $kind"; return 1; }
        [ "$value" -le "$maximum" ] || maximum=$value
    done
    [ "$cpu" -ge 2 ] && [ "$soc" -ge 1 ] || { fail 'CPU/SoC sensors missing'; return 1; }
    cooling=0
    for dev in "$THERMAL"/cooling_device*; do
        [ -r "$dev/type" ] && [ -r "$dev/cur_state" ] || continue
        kind=$(cat "$dev/type") || return 1
        case "$kind" in thermal-cpufreq-[0-2]) ;; *) continue;; esac
        state=$(cat "$dev/cur_state") || return 1
        case "$state" in 0|1) ;; *) fail "invalid cooling state $kind"; return 1;; esac
        if [ "$maximum" -ge 45000 ] && [ "$state" != 1 ]; then
            fail "cooling not applied at $maximum"; return 1
        fi
        cooling=$((cooling+1))
    done
    [ "$cooling" -eq 3 ] || { fail 'CPU cooling controls missing'; return 1; }
    echo "LYNX_HEALTH_OK battery_millidegrees=$battery capacity_percent=$capacity thermal_max_millidegrees=$maximum cooling_controls=$cooling"
}

case "${1:-}" in
    --once) health_once ;;
    --watch)
        mkdir "$STATE" || exit 1
        echo "$$" > "$STATE/pid"
        failures=0
        while :; do
            if health_once >> "$STATE/events.log" 2>&1; then
                failures=0
            else
                failures=$((failures+1))
                echo "LYNX_HEALTH_FAILURE count=$failures" >> "$STATE/events.log"
                if [ "$failures" -ge 3 ]; then
                    echo LYNX_HEALTH_SAFE_POWEROFF >> "$STATE/events.log"
                    echo '<2>LYNX_HEALTH_SAFE_POWEROFF' > /dev/kmsg
                    "$BB" poweroff -f
                    exit 2
                fi
            fi
            "$BB" sleep 5
        done
        ;;
    *) echo 'Usage: lynx-health-supervisor.sh --once|--watch' >&2; exit 2;;
esac
