. /etc/lynx/wifi-runtime.sh || stop
. /etc/lynx/wifi-local-supervise.sh || stop
# The independent timer protects the unmonitored interval after UFS/Wi-Fi
# bootstrap. It is cancelled only after V31 health monitoring is alive.
( $BB sleep 300; log 'LOCAL_BOOT_OUTER_DEADLINE_POWER_OFF'; $BB poweroff -f ) \
    >/run/lynx/local-boot-outer-timer.log 2>&1 </dev/null &
local_outer_timer=$!
printf '%s\n' "$local_outer_timer" > /run/lynx/local-boot-outer-timer.pid || stop
lynx_wifi_local_supervise || {
    log 'LOCAL_WIFI_FAILED; POWER_OFF_REQUESTED'
    $BB poweroff -f
    stop
}
local_token=$($BB cat /etc/lynx/session-token) || stop
[ -n "$local_token" ] || stop
printf '%s\n' "$local_token" > /run/lynx/local-boot-ready.tmp || stop
$BB mv /run/lynx/local-boot-ready.tmp /run/lynx/local-boot-ready || stop
. /etc/lynx/autonomous-health-local-handoff.sh || {
    log 'LOCAL_HEALTH_SCRIPT_MISSING; POWER_OFF_REQUESTED'
    $BB poweroff -f
    stop
}
lynx_autonomous_health_local_handoff || {
    log 'LOCAL_HEALTH_FAILED; POWER_OFF_REQUESTED'
    $BB poweroff -f
    stop
}
[ -f /run/lynx/health-bootstrap/ready ] || {
    log 'LOCAL_HEALTH_READY_MARKER_MISSING; POWER_OFF_REQUESTED'
    $BB poweroff -f
    stop
}
kill "$local_outer_timer" || {
    log 'LOCAL_BOOT_TIMER_CANCEL_FAILED; POWER_OFF_REQUESTED'
    $BB poweroff -f
    stop
}
wait "$local_outer_timer" 2>/dev/null || true
log 'LOCAL_WIFI_AND_HEALTH_READY; PERSISTENT_OPENRC_BEGIN'
. /etc/lynx/persistent-openrc-handoff.sh || {
    log 'LOCAL_PERSISTENT_HANDOFF_SCRIPT_MISSING; RESCUE_ACTIVE'
    stop
}
exec </dev/null 1>>/run/lynx/openrc-pid1-stdout.log 2>>/run/lynx/openrc-pid1-stderr.log
openrc_attempt=1
while [ "$openrc_attempt" -le 3 ]; do
    log "LOCAL_PERSISTENT_OPENRC_ATTEMPT attempt=$openrc_attempt"
    lynx_persistent_openrc_handoff
    openrc_result=$?
    [ "$openrc_result" = 2 ] || break
    [ ! -e /run/lynx/persistent-alpine ] || break
    [ "$openrc_attempt" -lt 3 ] || break
    log "LOCAL_PERSISTENT_OPENRC_GUARD_RETRY attempt=$openrc_attempt"
    $BB sleep 5
    openrc_attempt=$((openrc_attempt+1))
done
log 'LOCAL_PERSISTENT_OPENRC_REFUSED; MONITORED_BUSYBOX_RESCUE_ACTIVE'
stop
