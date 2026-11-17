#!/bin/sh
# Offline candidate: PID 1 calls this only after verified boot_a payload and
# local Wi-Fi/SSH readiness. It starts reviewed health monitoring without a
# host acknowledgement and leaves BusyBox as PID 1 on success.
lynx_autonomous_health_local_handoff() {
    local_archive=/usr/share/lynx/health-inputs.tar.gz
    local_hashfile=/usr/share/lynx/health-inputs.sha256
    local_root=/run/lynx/health-inputs
    local_result_file=/run/lynx/health-bootstrap-child-result
    local_token=$($BB cat /etc/lynx/session-token) || return 1
    local_ready=$($BB cat /run/lynx/local-boot-ready) || return 1
    [ -n "$local_token" ] && [ "$local_ready" = "$local_token" ] || return 1
    [ "$($BB cat /run/lynx/bootstrap-result)" = 0 ] || return 1
    local_expected=$($BB cat "$local_hashfile") || return 1
    case "$local_expected" in ''|*[!0-9a-f]*) return 1;; esac
    [ "${#local_expected}" -eq 64 ] || return 1
    local_actual=$($BB sha256sum "$local_archive") || return 1
    [ "${local_actual%% *}" = "$local_expected" ] || {
        log 'LOCAL_HEALTH_INPUT_ARCHIVE_HASH_MISMATCH'
        return 1
    }
    [ ! -e "$local_root" ] && [ ! -e "$local_result_file" ] || return 1
    $BB mkdir "$local_root" || return 1
    $BB tar -xzf "$local_archive" -C "$local_root" || return 1
    [ -r "$local_root/manifest.json" ] &&
        [ -r "$local_root/modules/lynx-battery-monitor.ko" ] || return 1

    IFS=' ' read -r local_started local_unused < /proc/uptime || return 1
    local_started=${local_started%%.*}
    case "$local_started" in ''|*[!0-9]*) return 1;; esac
    log 'LOCAL_HEALTH_BOOT_CHILD_BEGIN'
    (
        $BB sh /usr/libexec/lynx/autonomous-health-start.sh --run-local "$local_root"
        local_status=$?
        printf '%s\n' "$local_status" > "$local_result_file.tmp"
        $BB mv "$local_result_file.tmp" "$local_result_file"
    ) > /run/lynx/health-bootstrap-child.log 2>&1 &
    while :; do
        if [ -r "$local_result_file" ]; then
            IFS= read -r local_status < "$local_result_file" || return 1
            [ "$local_status" = 0 ] || {
                log "LOCAL_HEALTH_BOOT_CHILD_FAILED status=$local_status"
                return 1
            }
            break
        fi
        IFS=' ' read -r local_now local_unused < /proc/uptime || return 1
        local_now=${local_now%%.*}
        case "$local_now" in ''|*[!0-9]*) return 1;; esac
        [ "$local_now" -lt "$((local_started+190))" ] || {
            log 'LOCAL_HEALTH_BOOT_CHILD_DEADLINE; POWER_OFF_REQUESTED'
            $BB poweroff -f
            return 1
        }
        $BB sleep 1
    done
    $BB sh /run/lynx/lynx-health-supervisor.sh --once || return 1
    log 'LOCAL_HEALTH_BOOT_READY; BUSYBOX_RESCUE_PID1_ACTIVE'
}
