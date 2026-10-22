log 'V44_HEALTH_READY; THREE_PASS_OPENRC_TRIAL'
v44_failures=0
v44_passes=0
v44_attempted=0
while :; do
    IFS=' ' read -r v40_uptime v40_unused < /proc/uptime || stop
    v40_uptime=${v40_uptime%%.*}
    case "$v40_uptime" in ''|*[!0-9]*) stop;; esac
    [ "$v40_uptime" -lt 300 ] || break
    if $BB sh /run/lynx/lynx-health-supervisor.sh --once > /run/lynx/v44-postcheck.log 2>&1; then
        v44_failures=0
        v44_passes=$((v44_passes+1))
        if [ "$v44_passes" -ge 3 ] && [ "$v44_attempted" = 0 ]; then
            v44_attempted=1
            lynx_bootdiag_append HANDOFF_BEGIN || {
                log 'V44_HANDOFF_BEGIN_RECORD_FAILED; POWER_OFF_REQUESTED'
                $BB poweroff -f
                /bin/boot-proof-reboot
                stop
            }
            if [ -r /etc/lynx/persistent-openrc-handoff.sh ] &&
               . /etc/lynx/persistent-openrc-handoff.sh; then
                exec </dev/null 1>>/run/lynx/openrc-pid1-stdout.log 2>>/run/lynx/openrc-pid1-stderr.log
                lynx_persistent_openrc_handoff
            fi
            log 'V44_LOCAL_OPENRC_REFUSED; BOUNDED_BUSYBOX_RESCUE_ACTIVE'
            lynx_bootdiag_append HANDOFF_REFUSED || true
        fi
    else
        v44_failures=$((v44_failures+1))
        v44_passes=0
        log "V44_POSTCHECK_SAMPLE_FAILED count=$v44_failures"
        [ "$v44_failures" -lt 3 ] || {
            lynx_bootdiag_append HEALTH_FAIL_POSTCHECK || true
            $BB poweroff -f
            /bin/boot-proof-reboot
            stop
        }
    fi
    $BB sleep 5
done
lynx_bootdiag_append END || log 'V44_END_RECORD_FAILED'
log 'V44_OBSERVATION_COMPLETE; POWER_OFF_REQUESTED'
$BB poweroff -f
/bin/boot-proof-reboot
stop
