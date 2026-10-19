#!/bin/sh
# Called by init after the verified two-stage stock module bootstrap.
# Keep rescue Wi-Fi/SSH alive without requiring Nexus acknowledgement.
lynx_wifi_local_supervise() {
    [ -c /dev/null ] || return 1
    [ ! -e /run/lynx/worker-result ] || return 1
    IFS=' ' read -r wifi_start wifi_unused < /proc/uptime || return 1
    wifi_start=${wifi_start%%.*}
    case "$wifi_start" in ''|*[!0-9]*) return 1;; esac
    (
        lynx_wifi_worker
        wifi_result=$?
        printf '%s\n' "$wifi_result" > /run/lynx/worker-result.tmp
        $BB mv /run/lynx/worker-result.tmp /run/lynx/worker-result
    ) >>/run/lynx/boot.log 2>&1 </dev/null &
    wifi_worker_pid=$!
    log "LOCAL_WIFI_WORKER_STARTED pid=$wifi_worker_pid deadline_boot_seconds=$((wifi_start+240))"
    while :; do
        if [ -r /run/lynx/worker-result ]; then
            IFS= read -r wifi_result < /run/lynx/worker-result || return 1
            [ "$wifi_result" = 0 ] && [ -r /run/lynx/ssh-ready ] &&
                [ "$(cat /run/lynx/ssh-ready)" = ready ] || return 1
            log 'LOCAL_WIFI_SSH_READY'
            return 0
        fi
        IFS=' ' read -r wifi_now wifi_unused < /proc/uptime || return 1
        wifi_now=${wifi_now%%.*}
        case "$wifi_now" in ''|*[!0-9]*) return 1;; esac
        [ "$wifi_now" -lt "$((wifi_start+240))" ] || {
            log 'LOCAL_WIFI_DEADLINE'
            return 1
        }
        $BB sleep 1
    done
}
