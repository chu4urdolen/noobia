#!/bin/sh
# Supervised, bounded recovery of userland services. Never change charger or
# thermal controls; loss of the independent safety guards triggers power-off.
set -eu
BB=/bin/busybox
RUN=/run/lynx
INTERVAL=30
MAX_RETRIES=3

event() {
    printf 'LYNX_MAINTENANCE %s\n' "$*"
    $BB logger -p daemon.err -t lynx-maintenance "$*" 2>/dev/null || true
}

safety_ok() {
    /sbin/rc-service lynx-health status >/dev/null 2>&1 &&
        /sbin/rc-service lynx-battery-reserve status >/dev/null 2>&1
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
            if safety_ok; then
                safety_fail=0
            else
                safety_fail=$((safety_fail+1))
                event "SAFETY_GUARD_FAILED consecutive=$safety_fail"
                [ "$safety_fail" -lt 2 ] || shutdown_safely safety_guard_failed
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
