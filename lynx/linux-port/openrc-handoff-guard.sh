#!/bin/sh
# Fail-closed proof that the live V19 safety watchers are still running before
# any caller is allowed to replace BusyBox PID 1 with Alpine OpenRC.
# This guard only reads state. It does not mount, load modules, or hand off.
set -eu
BB=/bin/busybox
RUN=/run/lynx
SYS=/sys
THERMAL=$SYS/class/thermal
PROC=/proc
ETC=/etc/lynx
THERMAL_WATCH_SHA=822ec22915db93ac6a00a6d98356bc11c8d9265530e9e4183a6e68b30814df8a
BATTERY_WATCH_SHA=8d2d912ef5b42456709b0b1feb058e57e9b8f67b0c41a4580d40224dc18d5ce7
COOLING_WATCH_SHA=ed1ede4e1d5628ae87c394e8106398703707f0805353f18adf01be2b95ef8fd8

fail() { echo "OPENRC_HANDOFF_REFUSED $*" >&2; return 1; }

require_process() {
    pidfile=$1 expected=$2
    [ -r "$pidfile" ] || fail "missing pidfile $pidfile" || return 1
    pid=$(cat "$pidfile") || return 1
    case "$pid" in ''|*[!0-9]*) fail "invalid pid in $pidfile"; return 1;; esac
    kill -0 "$pid" 2>/dev/null || { fail "dead process $pid"; return 1; }
    tr '\000' '\n' < "$PROC/$pid/cmdline" | grep -Fx "$expected" >/dev/null || {
        fail "pid $pid does not run $expected"; return 1;
    }
}

lynx_openrc_handoff_guard() {
    token=$(cat "$ETC/session-token") || return 1
    [ -n "$token" ] || { fail 'empty boot token'; return 1; }
    case "${LYNX_OPENRC_AUTHORITY:-host}" in
        host)
            [ -r "$RUN/host-confirmed" ] || { fail 'pinned host has not confirmed this boot'; return 1; }
            IFS= read -r confirmed < "$RUN/host-confirmed" || return 1
            [ "$confirmed" = "$token" ] || { fail 'host confirmation token mismatch'; return 1; }
            if [ "${LYNX_OPENRC_ARMING:-0}" != 1 ]; then
                [ -r "$RUN/openrc-handoff-ready" ] || { fail 'host has not armed the OpenRC handoff'; return 1; }
                IFS= read -r ready < "$RUN/openrc-handoff-ready" || return 1
                [ "$ready" = "$token" ] || { fail 'handoff token mismatch'; return 1; }
            fi;;
        local)
            [ -r "$RUN/local-boot-ready" ] || { fail 'local init marker absent'; return 1; }
            IFS= read -r ready < "$RUN/local-boot-ready" || return 1
            [ "$ready" = "$token" ] || { fail 'local init token mismatch'; return 1; }
            [ "$(cat "$RUN/bootstrap-result")" = 0 ] || { fail 'stock bootstrap incomplete'; return 1; }
            [ -f "$RUN/health-bootstrap/ready" ] || { fail 'automatic health startup incomplete'; return 1; }
            [ -f "$RUN/ssh-ready" ] || { fail 'local SSH startup incomplete'; return 1; };;
        *) fail 'invalid handoff authority'; return 1;;
    esac

    echo "$THERMAL_WATCH_SHA  $RUN/thermal-watch.sh" | sha256sum -c - >/dev/null || { fail 'thermal watcher source hash differs'; return 1; }
    echo "$BATTERY_WATCH_SHA  $RUN/battery-watch.sh" | sha256sum -c - >/dev/null || { fail 'battery watcher source hash differs'; return 1; }
    echo "$COOLING_WATCH_SHA  $RUN/thermal-cooling-watch.sh" | sha256sum -c - >/dev/null || { fail 'cooling watcher source hash differs'; return 1; }
    require_process "$RUN/thermal-watch.pid" /run/lynx/thermal-watch.sh || return 1
    require_process "$RUN/battery-watch.pid" /run/lynx/battery-watch.sh || return 1
    require_process "$RUN/thermal-cooling-watch/pid" /run/lynx/thermal-cooling-watch.sh || return 1
    [ -d "$SYS/module/lynx_battery_monitor" ] || { fail 'identified battery monitor module is not loaded'; return 1; }
    [ -r "$SYS/bus/i2c/devices/7-0055/battery_snapshot" ] || { fail 'battery gauge snapshot is unavailable'; return 1; }
    [ -f "$RUN/thermal-watch.ready" ] || { fail 'thermal sensors are not ready'; return 1; }
    [ -f "$RUN/thermal-cooling-watch/ready" ] || { fail 'soft throttle is not ready'; return 1; }

    # Demand a recent, error-free reading from the exact battery gauge already
    # identified for Lynx. A missing/stale sample is never interpreted as cool.
    now=$(cut -d. -f1 "$PROC/uptime") || return 1
    sample=$(sed -n 's/^sample_uptime_seconds=//p' "$RUN/battery-last") || return 1
    sample=${sample%%.*}
    case "$now:$sample" in *[!0-9:]*) fail 'invalid battery sample age'; return 1;; esac
    [ "$now" -ge "$sample" ] && [ "$((now-sample))" -le 15 ] || { fail 'battery sample is stale'; return 1; }
    for field in gauge_device_type temperature_millidegrees_celsius temperature_error voltage_error current_error capacity_error capacity_percent; do
        grep -Eq "^${field}=-?[0-9]+$" "$RUN/battery-last" || { fail "missing/invalid battery field $field"; return 1; }
    done
    grep -Fxq 'gauge_device_type=42495' "$RUN/battery-last" || { fail 'unexpected battery gauge'; return 1; }
    for field in temperature_error voltage_error current_error capacity_error; do
        grep -Fxq "$field=0" "$RUN/battery-last" || { fail "battery gauge error: $field"; return 1; }
    done
    battery_temp=$(sed -n 's/^temperature_millidegrees_celsius=//p' "$RUN/battery-last")
    battery_capacity=$(sed -n 's/^capacity_percent=//p' "$RUN/battery-last")
    case "$battery_temp:$battery_capacity" in *[!0-9:]*) fail 'invalid battery temperature/capacity'; return 1;; esac
    [ "$battery_temp" -lt 48000 ] || { fail 'battery temperature is not below 48C'; return 1; }
    [ "$battery_capacity" -ge 10 ] && [ "$battery_capacity" -le 100 ] || { fail 'battery charge is below 10% or invalid'; return 1; }

    # Repeat the thermal reading check at the handoff boundary. Keep the stricter
    # <40C initial condition used by the tested cooling watcher.
    thermal_count=0 thermal_max=0 cpu_count=0 soc_count=0
    for zone in "$THERMAL"/thermal_zone*; do
        [ -r "$zone/type" ] && [ -r "$zone/temp" ] || continue
        kind=$(cat "$zone/type") || return 1
        case "$kind" in soc_max) soc_count=$((soc_count+1));; cpu_*) cpu_count=$((cpu_count+1));; *) continue;; esac
        value=$(cat "$zone/temp") || return 1
        case "$value" in ''|*[!0-9]*) fail "invalid thermal reading $kind"; return 1;; esac
        [ "$value" -gt 0 ] && [ "$value" -le 125000 ] || { fail "out-of-range thermal reading $kind"; return 1; }
        [ "$value" -le "$thermal_max" ] || thermal_max=$value
        thermal_count=$((thermal_count+1))
    done
    [ "$soc_count" -ge 1 ] && [ "$cpu_count" -ge 2 ] || { fail 'CPU/SoC sensor inventory incomplete'; return 1; }
    [ "$thermal_count" -ge 3 ] && [ "$thermal_max" -lt 48000 ] || { fail 'CPU/SoC temperatures must all be below 48C'; return 1; }

    cooling_count=0
    for dev in "$THERMAL"/cooling_device*; do
        [ -r "$dev/type" ] && [ -r "$dev/cur_state" ] || continue
        kind=$(cat "$dev/type") || return 1
        case "$kind" in thermal-cpufreq-[0-2]) ;; *) continue;; esac
        state=$(cat "$dev/cur_state") || return 1
        case "$state" in 0|1) ;; *) fail "invalid cooling state $kind"; return 1;; esac
        cooling_count=$((cooling_count+1))
    done
    [ "$cooling_count" -eq 3 ] || { fail 'expected exactly three CPU cooling controls'; return 1; }
    echo "OPENRC_HANDOFF_GUARD_PASS battery_millidegrees=$battery_temp thermal_max_millidegrees=$thermal_max cooling_controls=$cooling_count"
}

case "$0" in
    */openrc-handoff-guard.sh)
        if [ "${1:-}" = --check ]; then
            lynx_openrc_handoff_guard
        else
            echo 'Usage: openrc-handoff-guard.sh --check' >&2
            exit 2
        fi
        ;;
esac
