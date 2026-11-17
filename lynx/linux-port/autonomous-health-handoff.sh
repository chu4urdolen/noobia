#!/bin/sh
# Offline V24 design. Sourced by native PID 1 only after V19 Wi-Fi supervision
# has confirmed the pinned host. Start the health stage in a bounded child,
# then permit the existing guarded OpenRC handoff. No partition writes.
lynx_autonomous_health_handoff() {
    archive=/usr/share/lynx/health-inputs.tar.gz
    hashfile=/usr/share/lynx/health-inputs.sha256
    root=/run/lynx/health-inputs
    child_result=/run/lynx/health-bootstrap-child-result
    token=$($BB cat /etc/lynx/session-token) || return 1
    confirmed=$($BB cat /run/lynx/host-confirmed) || return 1
    [ -n "$token" ] && [ "$confirmed" = "$token" ] || return 1
    expected=$($BB cat "$hashfile") || return 1
    case "$expected" in ''|*[!0-9a-f]*) return 1;; esac
    [ "${#expected}" -eq 64 ] || return 1
    actual=$($BB sha256sum "$archive") || return 1
    [ "${actual%% *}" = "$expected" ] || {
        log 'HEALTH_INPUT_ARCHIVE_HASH_MISMATCH'
        return 1
    }
    [ ! -e "$root" ] && [ ! -e "$child_result" ] || return 1
    $BB mkdir "$root" || return 1
    # The exact archive bytes were checked before extraction. tar's exit status
    # must report complete extraction; no member can escape the archive root.
    $BB tar -xzf "$archive" -C "$root" || return 1
    [ -r "$root/manifest.json" ] &&
        [ -r "$root/modules/lynx-battery-monitor.ko" ] || return 1

    IFS=' ' read -r started unused < /proc/uptime || return 1
    started=${started%%.*}
    case "$started" in ''|*[!0-9]*) return 1;; esac
    log 'HEALTH_BOOT_CHILD_BEGIN'
    (
        $BB sh /usr/libexec/lynx/autonomous-health-start.sh --run "$root"
        status=$?
        printf '%s\n' "$status" > "$child_result.tmp"
        $BB mv "$child_result.tmp" "$child_result"
    ) > /run/lynx/health-bootstrap-child.log 2>&1 &
    while :; do
        if [ -r "$child_result" ]; then
            IFS= read -r result < "$child_result" || return 1
            [ "$result" = 0 ] || { log "HEALTH_BOOT_CHILD_FAILED status=$result"; return 1; }
            break
        fi
        IFS=' ' read -r now unused < /proc/uptime || return 1
        now=${now%%.*}
        case "$now" in ''|*[!0-9]*) return 1;; esac
        [ "$now" -lt "$((started+190))" ] || {
            log 'HEALTH_BOOT_CHILD_DEADLINE; POWER_OFF_REQUESTED'
            $BB poweroff -f
            return 1
        }
        $BB sleep 1
    done
    $BB sh /run/lynx/lynx-health-supervisor.sh --once || return 1
    printf '%s\n' "$token" > /run/lynx/openrc-handoff-ready.tmp || return 1
    $BB mv /run/lynx/openrc-handoff-ready.tmp /run/lynx/openrc-handoff-ready || return 1
    log 'HEALTH_BOOT_READY; OPENRC_GATE_ARMED'
    . /etc/lynx/openrc-handoff.sh || return 1
    lynx_openrc_handoff
}
