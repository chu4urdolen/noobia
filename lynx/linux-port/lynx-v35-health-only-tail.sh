. /etc/lynx/wifi-runtime.sh || stop
. /etc/lynx/wifi-local-supervise.sh || stop
# Preserve V34's bounded local Wi-Fi and V31 health startup. This diagnostic
# intentionally stops before the persistent Alpine handoff.
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
$BB sh /run/lynx/lynx-health-supervisor.sh --once || {
    log 'HEALTH_ONLY_POSTCHECK_REFUSED; POWER_OFF_REQUESTED'
    $BB poweroff -f
    stop
}
log 'LOCAL_HEALTH_READY; BUSYBOX_PID1_OBSERVATION_WINDOW'
# Health monitoring remains active. The fixed limit protects the battery if
# Nexus cannot reconnect, while the 10-minute window lets it collect traces.
( $BB sleep 600; log 'HEALTH_ONLY_OBSERVATION_DEADLINE_POWER_OFF';
  $BB poweroff -f; /bin/boot-proof-reboot ) \
    >/run/lynx/health-only-observation-timer.log 2>&1 </dev/null &
printf '%s\n' "$!" > /run/lynx/health-only-observation-timer.pid || stop
stop
