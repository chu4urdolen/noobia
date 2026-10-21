. /etc/lynx/wifi-runtime.sh || stop
. /etc/lynx/wifi-local-supervise.sh || stop
# Diagnostic only: leave health and Alpine untouched. If SSH survives past the
# V36 loss window, the autonomous health path becomes the next suspect.
# This image is never for unattended daily use.
( $BB sleep 230; log 'WIFI_ONLY_OUTER_DEADLINE_POWER_OFF';
  $BB poweroff -f; /bin/boot-proof-reboot ) \
    >/run/lynx/wifi-only-outer-timer.log 2>&1 </dev/null &
wifi_only_timer=$!
printf '%s\n' "$wifi_only_timer" > /run/lynx/wifi-only-outer-timer.pid || stop
lynx_wifi_local_supervise || {
    log 'WIFI_ONLY_WORKER_FAILED; POWER_OFF_REQUESTED'
    $BB poweroff -f
    /bin/boot-proof-reboot
    stop
}
log 'WIFI_ONLY_SSH_READY; HEALTH_NOT_STARTED'
while :; do
    IFS=' ' read -r wifi_only_uptime wifi_only_unused < /proc/uptime || stop
    wifi_only_uptime=${wifi_only_uptime%%.*}
    case "$wifi_only_uptime" in ''|*[!0-9]*) stop;; esac
    [ "$wifi_only_uptime" -lt 190 ] || break
    wifi_only_supplies=0
    for wifi_only_supply in /sys/class/power_supply/*; do
        [ -r "$wifi_only_supply/online" ] || continue
        IFS= read -r wifi_only_online < "$wifi_only_supply/online" || stop
        [ "$wifi_only_online" = 0 ] || {
            log 'WIFI_ONLY_CHARGER_ONLINE; POWER_OFF_REQUESTED'
            $BB poweroff -f
            /bin/boot-proof-reboot
            stop
        }
        wifi_only_supplies=$((wifi_only_supplies+1))
    done
    [ "$wifi_only_supplies" -ge 1 ] || {
        log 'WIFI_ONLY_CHARGER_STATE_MISSING; POWER_OFF_REQUESTED'
        $BB poweroff -f
        /bin/boot-proof-reboot
        stop
    }
    log "WIFI_ONLY_STILL_ALIVE uptime=$wifi_only_uptime"
    $BB sleep 5
done
log 'WIFI_ONLY_OBSERVATION_COMPLETE; POWER_OFF_REQUESTED'
$BB poweroff -f
/bin/boot-proof-reboot
stop
