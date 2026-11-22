log 'V54_HEALTH_READY; RETRYING_OPENRC_HANDOFF_NO_POWEROFF'
# V54 candidate (Gwyn, 2026-11-23) - replaces lynx-v44-local-openrc-tail.sh.
# NOT BUILT, NOT FLASHED: source for Aria's reviewed boot-image packet
# (docs/LYNX-BOOT-NO-POWEROFF-PACKET-20261123.md).
#
# V44 powered Lynx off in three places: 3 failed health samples, the end of
# the 300 s observation window, and a failed HANDOFF_BEGIN record. On
# 2026-11-22/23 a refused hand-off (a hash mismatch, then a warm boot over
# the guard's 48 C limit) turned into a power-off at 300 s on every boot and
# finally a bootloader fastboot. Principle 10: never power off on stress.
#
# V54: the BusyBox rescue stays up (SSH reachable) for as long as it takes.
# - 3 consecutive health passes -> attempt the hand-off; if refused, wait
#   V54_RETRY_S and try again (e.g. after cooling below the guard limit).
# - failed health samples apply CPU soft throttling and keep waiting.
# - no poweroff, no reboot, ever.
V54_RETRY_S=30
v44_failures=0
v44_passes=0
v54_next_attempt=0
v54_attempts=0
while :; do
    IFS=' ' read -r v40_uptime v40_unused < /proc/uptime || { $BB sleep 5; continue; }
    v40_uptime=${v40_uptime%%.*}
    case "$v40_uptime" in ''|*[!0-9]*) $BB sleep 5; continue;; esac
    if $BB sh /run/lynx/lynx-health-supervisor.sh --once > /run/lynx/v44-postcheck.log 2>&1; then
        v44_failures=0
        v44_passes=$((v44_passes+1))
        if [ "$v44_passes" -ge 3 ] && [ "$v40_uptime" -ge "$v54_next_attempt" ]; then
            v54_attempts=$((v54_attempts+1))
            # A refused attempt leaves /run/lynx/persistent-alpine behind (and
            # may leave binds or the disk mounted); the hand-off refuses to
            # start while either exists, so clear them before retrying.
            if [ "$v54_attempts" -gt 1 ]; then
                for v54_point in run dev sys proc; do
                    $BB umount /run/lynx/persistent-alpine/$v54_point 2>/dev/null || true
                done
                $BB umount /run/lynx/persistent-alpine 2>/dev/null || true
                $BB rmdir /run/lynx/persistent-alpine 2>/dev/null || true
            fi
            lynx_bootdiag_append HANDOFF_BEGIN || log 'V54_HANDOFF_BEGIN_RECORD_FAILED; CONTINUING'
            if [ -r /etc/lynx/persistent-openrc-handoff.sh ] &&
               . /etc/lynx/persistent-openrc-handoff.sh; then
                exec </dev/null 1>>/run/lynx/openrc-pid1-stdout.log 2>>/run/lynx/openrc-pid1-stderr.log
                lynx_persistent_openrc_handoff      # exec's openrc-init on success
            fi
            log "V54_LOCAL_OPENRC_REFUSED attempt=$v54_attempts; RESCUE_STAYS_UP; RETRY_IN_${V54_RETRY_S}S"
            lynx_bootdiag_append HANDOFF_REFUSED || true
            v54_next_attempt=$((v40_uptime + V54_RETRY_S))
            v44_passes=0
        fi
    else
        v44_failures=$((v44_failures+1))
        v44_passes=0
        log "V54_POSTCHECK_SAMPLE_FAILED count=$v44_failures; QUIESCE_NOT_POWEROFF"
        if [ "$v44_failures" -ge 3 ]; then
            for v54_dev in /sys/class/thermal/cooling_device*; do
                [ -f "$v54_dev/cur_state" ] && echo 1 > "$v54_dev/cur_state" 2>/dev/null || true
            done
        fi
    fi
    $BB sleep 5
done
