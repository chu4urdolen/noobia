#!/bin/sh
# Candidate for an independent boot. Source after the proven V19 Wi-Fi runtime.
# Its worker is unchanged; the success condition is local Wi-Fi/SSH readiness
# rather than a Nexus acknowledgement. Failure uses the existing single
# supported return-to-Fastboot helper. No partition writes.
lynx_wifi_supervise_local() {
    [ -c /dev/null ] || return 1
    lynx_clock || return 1
    local_start=$seconds
    (
        lynx_wifi_worker
        local_result=$?
        printf '%s\n' "$local_result" > /run/lynx/worker-result.tmp
        $BB mv /run/lynx/worker-result.tmp /run/lynx/worker-result
    ) >> /run/lynx/boot.log 2>&1 &
    log "LOCAL_WIFI_WORKER_STARTED deadline_boot_seconds=$((local_start+240))"
    while :; do
        lynx_clock || return 1
        # Discovery is advisory: SSH stays usable when Nexus is absent, but
        # an observer must learn a changed DHCP address before worker exit.
        if [ -f /run/lynx/ssh-ready ]; then
            local_beacon_host=$($BB cat /etc/lynx/host-ip 2>/dev/null) || local_beacon_host=
            local_beacon_token=$($BB cat /etc/lynx/session-token 2>/dev/null) || local_beacon_token=
            if [ -n "$local_beacon_host" ] && [ -n "$local_beacon_token" ]; then
                printf 'LYNX_HELLO %s\n' "$local_beacon_token" |
                    /usr/bin/nc -u -w 1 "$local_beacon_host" 5514 || true
            fi
        fi
        if [ -f /run/lynx/worker-result ]; then
            IFS= read -r local_result < /run/lynx/worker-result || return 1
            case "$local_result" in ''|*[!0-9]*) return 1;; esac
            if [ "$local_result" != 0 ]; then
                log "LOCAL_WIFI_WORKER_FAILED status=$local_result"
                break
            fi
            if [ -f /run/lynx/ssh-ready ] && [ -r /run/lynx/ssh.pid ] &&
                    [ -r /run/lynx/address ] && [ -r /run/lynx/interface ]; then
                IFS= read -r local_pid < /run/lynx/ssh.pid || return 1
                IFS= read -r local_address < /run/lynx/address || return 1
                IFS= read -r local_interface < /run/lynx/interface || return 1
                case "$local_pid" in ''|*[!0-9]*) return 1;; esac
                case "$local_address" in ''|*[!0-9.]*) return 1;; esac
                case "$local_interface" in wlan0|wlan1) ;; *) return 1;; esac
                [ -d "/sys/class/net/$local_interface" ] &&
                    kill -0 "$local_pid" 2>/dev/null &&
                    $BB tr '\000' '\n' < "/proc/$local_pid/cmdline" |
                    $BB grep -Fxq /usr/sbin/dropbear || break
                log "LOCAL_WIFI_SSH_READY interface=$local_interface address=$local_address"
                return 0
            fi
        fi
        [ "$seconds" -lt "$((local_start+240))" ] || {
            log 'LOCAL_WIFI_STARTUP_DEADLINE'
            break
        }
        $BB sleep 1
    done
    log 'LOCAL_WIFI_REQUESTING_ONE_SUPPORTED_BOOTLOADER_REBOOT'
    /bin/boot-proof-reboot
    log 'LOCAL_WIFI_REBOOT_RETURNED; NO_RETRY'
    return 1
}
