#!/bin/sh
# Supervised, bounded recovery of userland services. Never change charger or
# thermal controls; loss of the independent safety guards triggers power-off.
set -eu
BB=/bin/busybox
RUN=/run/lynx
INTERVAL=30
MAX_RETRIES=3
GUARD_SWITCH=/etc/lynx/power-thermal-guard.disable
SAFETY_FAILS_TO_ACT=10

event() {
    printf 'LYNX_MAINTENANCE %s\n' "$*"
    $BB logger -p daemon.err -t lynx-maintenance "$*" 2>/dev/null || true
}

recent_health_ok() {
    state=$RUN/health-supervisor
    [ -r "$state/pid" ] && [ -r "$state/events.log" ] || return 1
    pid=$(cat "$state/pid") || return 1
    case "$pid" in ''|*[!0-9]*) return 1;; esac
    kill -0 "$pid" 2>/dev/null || return 1
    now=$(date -u +%s) || return 1
    updated=$($BB stat -c %Y "$state/events.log") || return 1
    case "$now:$updated" in *[!0-9:]*) return 1;; esac
    [ "$now" -ge "$updated" ] && [ "$((now-updated))" -le 12 ] || return 1
    $BB tail -n 6 "$state/events.log" | $BB grep -q '^LYNX_HEALTH_OK '
}

safety_ok() {
    health_rc=0
    reserve_rc=0
    /sbin/rc-service lynx-health status >/dev/null 2>&1 || health_rc=$?
    /sbin/rc-service lynx-battery-reserve status >/dev/null 2>&1 || reserve_rc=$?
    if [ "$health_rc" -eq 0 ] && [ "$reserve_rc" -eq 0 ]; then
        return 0
    fi

    # A service status failure may mean a dead watcher, a stale sample, or a
    # transient sensor read. Preserve the independent watchers and diagnose.
    health_once_rc=0
    reserve_once_rc=0
    health_script=/usr/libexec/lynx-health-supervisor.sh
    [ -r "$health_script" ] || health_script=$RUN/lynx-health-supervisor.sh
    health_detail=$(/bin/sh "$health_script" --once 2>&1) || health_once_rc=$?
    reserve_detail=$(/bin/sh /usr/libexec/lynx-battery-reserve.sh --once 2>&1) || reserve_once_rc=$?
    health_detail=$(printf '%s' "$health_detail" | $BB tr '\n' ' ' | $BB cut -c 1-160)
    reserve_detail=$(printf '%s' "$reserve_detail" | $BB tr '\n' ' ' | $BB cut -c 1-160)
    event "SAFETY_PROBE health_status=$health_rc reserve_status=$reserve_rc health_once=$health_once_rc reserve_once=$reserve_once_rc health_detail=$health_detail reserve_detail=$reserve_detail"

    # The cooler polls every five seconds. A brief rise through 45 C can
    # precede its next sample; the independent health supervisor has already
    # demonstrated recovery if its recent log contains a healthy sample.
    # Never defer a missing process, reserve failure, stale heartbeat, or
    # temperature at or above 55 C. The independent thermal watcher stops
    # at 60 C and the health watcher still shuts down after three failures.
    if [ "$health_rc" -ne 0 ] && [ "$reserve_rc" -eq 0 ]; then
        case "$health_detail" in
            'LYNX_HEALTH_REFUSED cooling not applied at '*)
                temperature=${health_detail##*at }
                case "$temperature" in
                    ''|*[!0-9]*) ;;
                    *) if [ "$temperature" -lt 55000 ] && recent_health_ok; then
                           event "SAFETY_PROBE_DEFERRED cooling_transition_mC=$temperature"
                           return 0
                       fi;;
                esac;;
        esac
    fi
    return 1
}

wifi_address() {
    [ "$(cat /sys/class/net/wlan0/carrier 2>/dev/null)" = 1 ] || return 1
    address=$(/sbin/ip -4 addr show dev wlan0 |
        $BB sed -n 's/^[[:space:]]*inet \(192\.168\.100\.[0-9]*\)\/.*/\1/p' |
        $BB head -n 1) || return 1
    [ -n "$address" ] || return 1
    printf '%s\n' "$address"
}

wifi_snapshot() {
    carrier=$(cat /sys/class/net/wlan0/carrier 2>/dev/null) || carrier=unknown
    case "$carrier" in 0|1) ;; *) carrier=unknown;; esac
    ipv4=$(/sbin/ip -4 addr show dev wlan0 2>/dev/null |
        $BB sed -n 's/^[[:space:]]*inet \(192\.168\.100\.[0-9]*\)\/.*/\1/p' |
        $BB head -n 1) || ipv4=''
    [ -n "$ipv4" ] || ipv4=none
    link=$($BB timeout 3 /usr/sbin/iw dev wlan0 link 2>/dev/null |
        $BB head -n 1) || link=''
    case "$link" in
        'Connected to '*) link=connected ;;
        'Not connected.'*) link=disconnected ;;
        *) link=unknown ;;
    esac
    printf 'carrier=%s ipv4=%s nl80211_link=%s' "$carrier" "$ipv4" "$link"
}

recover_ssh() {
    address=$(wifi_address) || return 1
    [ -n "$address" ] || return 1
    pidfile=$RUN/alpine-dropbear-2222.pid
    if [ -e "$pidfile" ]; then
        pid=$(cat "$pidfile") || return 1
        case "$pid" in ''|*[!0-9]*) return 1;; esac
        kill -0 "$pid" 2>/dev/null && return 1
        rm "$pidfile" || return 1
    fi
    if $BB netstat -lnt | $BB grep -Eq ':2222[[:space:]]'; then
        return 1
    fi
    [ -s /etc/dropbear/lynx_ed25519_host_key ] &&
        [ -s /root/.ssh/authorized_keys ] || return 1
    /usr/sbin/dropbear -E -s -j -k -p "$address:2222" -P "$pidfile" \
        -r /etc/dropbear/lynx_ed25519_host_key </dev/null >> "$RUN/alpine-dropbear-2222.log" 2>&1 || return 1
    $BB sleep 1
    /sbin/rc-service lynx-dropbear status >/dev/null 2>&1
}

recover_logs() {
    /sbin/rc-service lynx-local-logs restart >/dev/null 2>&1 &&
        /sbin/rc-service lynx-local-logs status >/dev/null 2>&1
}

shutdown_safely() {
    reason=$1
    event "SAFE_POWEROFF reason=$reason"
    printf '<2>LYNX_MAINTENANCE_SAFE_POWEROFF reason=%s\n' "$reason" > /dev/kmsg || true
    /sbin/openrc-shutdown --poweroff now || true
    $BB sleep 15
    $BB poweroff -f
}

check_once() {
    safety_ok || return 1
    /sbin/rc-service lynx-local-logs status >/dev/null 2>&1 || return 1
    /sbin/rc-service lynx-wifi status >/dev/null 2>&1 || return 1
    /sbin/rc-service lynx-dropbear status >/dev/null 2>&1 || return 1
    printf 'LYNX_MAINTENANCE_OK boot_id=%s\n' "$(cat /proc/sys/kernel/random/boot_id)"
}

case "${1:-}" in
    --once) check_once ;;
    --event-proof) event 'LYNX_MAINTENANCE_EVENT_PROOF' ;;
    --wifi-snapshot) wifi_snapshot; printf '\n' ;;
    --watch)
        safety_fail=0
        log_fail=0
        ssh_fail=0
        wifi_fail=0
        while :; do
            # Tom 2026-11-22: guards are switched off by $GUARD_SWITCH, and when
            # on, one glitchy reading must never stop Lynx: only
            # SAFETY_FAILS_TO_ACT consecutive failures (5 min at 30 s) act.
            if [ -e "$GUARD_SWITCH" ]; then
                safety_fail=0
            elif safety_ok; then
                safety_fail=0
            else
                safety_fail=$((safety_fail+1))
                event "SAFETY_GUARD_FAILED consecutive=$safety_fail of $SAFETY_FAILS_TO_ACT"
                [ "$safety_fail" -lt "$SAFETY_FAILS_TO_ACT" ] || shutdown_safely safety_guard_failed
            fi
            if /sbin/rc-service lynx-local-logs status >/dev/null 2>&1; then
                log_fail=0
            elif [ "$log_fail" -lt "$MAX_RETRIES" ]; then
                log_fail=$((log_fail+1))
                event "LOCAL_LOGS_RESTART attempt=$log_fail"
                recover_logs && log_fail=0 || event 'LOCAL_LOGS_RECOVERY_FAILED'
            fi
            if /sbin/rc-service lynx-dropbear status >/dev/null 2>&1; then
                ssh_fail=0
            elif wifi_address >/dev/null 2>&1 && [ "$ssh_fail" -lt "$MAX_RETRIES" ]; then
                ssh_fail=$((ssh_fail+1))
                event "SSH_RECOVERY attempt=$ssh_fail"
                recover_ssh && ssh_fail=0 || event 'SSH_RECOVERY_FAILED'
            fi
            if ! /sbin/rc-service lynx-wifi status >/dev/null 2>&1; then
                if [ "$wifi_fail" = 0 ]; then
                    detail=$(wifi_snapshot) || detail=snapshot_failed
                    event "WIFI_DEGRADED $detail; RESCUE_AND_SAFETY_SERVICES_RETAINED"
                fi
                wifi_fail=1
            elif [ "$wifi_fail" = 1 ]; then
                event 'WIFI_RECOVERED'
                wifi_fail=0
            fi
            $BB sleep "$INTERVAL"
        done
        ;;
    *) echo 'Usage: lynx-maintenance-watch.sh --once|--watch' >&2; exit 2;;
esac
