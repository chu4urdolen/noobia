#!/bin/sh
# Optional, explicitly armed 98% MT6375 charge cap for Lynx Alpine.
# Never powers off, reboots, or changes charger voltage/current limits.
# Not enabled at boot until the live charger control is verified.
set -eu

BB=/bin/busybox
GAUGE=/sys/bus/i2c/devices/7-0055/battery_snapshot
STATUS=/sys/class/power_supply/11e01000.i2c:mt6375@34:chg/status
STATE=/run/lynx/charge-cap
STOP_AT=98
RESUME_AT=95
RESUME_TEMP_MAX=35000
SAMPLE_SECONDS=30

event() {
    printf 'LYNX_CHARGE_CAP %s\n' "$*"
    $BB logger -p daemon.notice -t lynx-charge-cap "$*" 2>/dev/null || true
}

snapshot() {
    [ -r "$GAUGE" ] || return 1
    sample=$($BB cat "$GAUGE") || return 1
    identity=$(printf '%s\n' "$sample" | $BB sed -n 's/^gauge_device_type=//p')
    capacity_error=$(printf '%s\n' "$sample" | $BB sed -n 's/^capacity_error=//p')
    temperature_error=$(printf '%s\n' "$sample" | $BB sed -n 's/^temperature_error=//p')
    capacity=$(printf '%s\n' "$sample" | $BB sed -n 's/^capacity_percent=//p')
    temperature=$(printf '%s\n' "$sample" | $BB sed -n 's/^temperature_millidegrees_celsius=//p')
    [ "$identity" = 42495 ] && [ "$capacity_error" = 0 ] &&
        [ "$temperature_error" = 0 ] || return 1
    case "$capacity:$temperature" in *[!0-9:]*|:*|*:) return 1;; esac
    [ "$capacity" -le 100 ] && [ "$temperature" -gt 0 ] &&
        [ "$temperature" -le 60000 ] || return 1
    printf '%s %s\n' "$capacity" "$temperature"
}

probe() {
    [ -r "$STATUS" ] || { event 'PROBE_FAILED status_unreadable'; return 1; }
    [ -w "$STATUS" ] || { event 'PROBE_FAILED status_not_writable'; return 1; }
    values=$(snapshot) || { event 'PROBE_FAILED gauge_invalid'; return 1; }
    status=$($BB cat "$STATUS") || { event 'PROBE_FAILED status_read_failed'; return 1; }
    set -- $values
    event "PROBE_OK capacity_percent=$1 temperature_millidegrees=$2 charger_status=$status"
}

apply_once() {
    [ -r "$STATUS" ] && [ -w "$STATUS" ] || {
        event 'CONTROL_UNAVAILABLE'; return 1;
    }
    values=$(snapshot) || { event 'GAUGE_INVALID; NO_WRITE'; return 1; }
    set -- $values
    capacity=$1 temperature=$2
    mode=unknown
    [ ! -r "$STATE" ] || mode=$($BB cat "$STATE") || return 1
    case "$mode" in unknown|stopped|charging) ;; *) event 'STATE_INVALID; NO_WRITE'; return 1;; esac
    if [ "$capacity" -ge "$STOP_AT" ]; then
        # In this matched kernel source, status=0 calls mt6375_chg_enable_charging(false).
        printf '0\n' > "$STATUS" || { event 'STOP_WRITE_FAILED'; return 1; }
        printf 'stopped\n' > "$STATE.tmp" && $BB mv "$STATE.tmp" "$STATE"
        [ "$mode" = stopped ] || event "STOP_REQUESTED capacity_percent=$capacity"
    elif [ "$mode" = stopped ] && [ "$capacity" -le "$RESUME_AT" ] &&
            [ "$temperature" -lt "$RESUME_TEMP_MAX" ]; then
        printf '1\n' > "$STATUS" || { event 'RESUME_WRITE_FAILED'; return 1; }
        printf 'charging\n' > "$STATE.tmp" && $BB mv "$STATE.tmp" "$STATE"
        event "RESUME_REQUESTED capacity_percent=$capacity temperature_millidegrees=$temperature"
    fi
}

case "${1:-}" in
    --probe)
        [ "$#" = 1 ] || exit 2
        probe
        ;;
    --apply-once)
        [ "$#" = 2 ] && [ "$2" = --armed ] || {
            event 'REFUSED; LIVE_CONTROL_PROOF_REQUIRED'; exit 2;
        }
        [ -d /run/lynx ] || exit 1
        probe || exit 1
        apply_once
        ;;
    --watch)
        [ "$#" = 2 ] && [ "$2" = --armed ] || {
            event 'REFUSED; LIVE_CONTROL_PROOF_REQUIRED'; exit 2;
        }
        [ -d /run/lynx ] || exit 1
        probe || exit 1
        while :; do
            apply_once || exit 1
            $BB sleep "$SAMPLE_SECONDS"
        done
        ;;
    *)
        echo 'Usage: lynx-charge-cap.sh --probe | --apply-once --armed | --watch --armed' >&2
        exit 2
        ;;
esac
