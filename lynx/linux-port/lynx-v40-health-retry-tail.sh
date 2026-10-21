. /etc/lynx/wifi-runtime.sh || stop
. /etc/lynx/wifi-local-supervise.sh || stop
lynx_bootdiag_append() {
    diag_stage=$1
    case "$diag_stage" in
        START|WIFI_READY|WIFI_FAILED|UPTIME_120|UPTIME_150|UPTIME_180|HEALTH_BEGIN|HEALTH_FAILED|HEALTH_FAIL_PRECHECK|HEALTH_FAIL_CHILD|HEALTH_FAIL_WATCHER|HEALTH_FAIL_BATTERY|HEALTH_FAIL_THERMAL|HEALTH_FAIL_POSTCHECK|HEALTH_FAIL_LOG|HEALTH_READY|CHARGER_ON|END) ;;
        *) return 1;;
    esac
    diag_boot_id=$($BB cat /proc/sys/kernel/random/boot_id) || return 1
    printf '%s\n' "$diag_boot_id" | $BB grep -Eq '^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$' || return 1
    IFS=' ' read -r diag_uptime diag_unused < /proc/uptime || return 1
    diag_uptime=${diag_uptime%%.*}
    case "$diag_uptime" in ''|*[!0-9]*) return 1;; esac
    $BB grep -Fx 'PARTNAME=userdata' /sys/class/block/sdc85/uevent >/dev/null || return 1
    [ "$($BB cat /sys/class/block/sdc85/size)" = 466026432 ] || return 1
    [ -b /dev/sdc85 ] || return 1
    ! $BB grep -Eq '^/dev/sdc85 |^/dev/block/by-name/userdata ' /proc/mounts || return 1
    diag_identity=$($BB blkid /dev/sdc85) || return 1
    case "$diag_identity" in
        *'LABEL="LYNXROOT"'*'UUID="13dc3665-b062-405e-b674-ceae8972fc0f"'*'TYPE="ext4"'*) ;;
        *) return 1;;
    esac
    diag_root=/run/lynx/bootdiag-root
    [ ! -e "$diag_root" ] || return 1
    $BB mkdir "$diag_root" || return 1
    if ! $BB mount -t ext4 -o rw,nosuid,nodev,noexec /dev/sdc85 "$diag_root"; then
        $BB rmdir "$diag_root"
        return 1
    fi
    diag_status=0
    [ ! -L "$diag_root/var" ] && [ ! -L "$diag_root/var/log" ] &&
        [ "$($BB cat "$diag_root/etc/alpine-release")" = 3.24.2 ] || diag_status=1
    if [ "$diag_status" = 0 ]; then
        diag_dir=$diag_root/var/log/lynx-bootdiag
        [ ! -L "$diag_dir" ] && $BB mkdir -p "$diag_dir" || diag_status=1
    fi
    if [ "$diag_status" = 0 ]; then
        diag_file=$diag_dir/$diag_boot_id.log
        [ ! -L "$diag_file" ] || diag_status=1
        if [ -f "$diag_file" ]; then
            diag_bytes=$($BB wc -c < "$diag_file") || diag_status=1
            case "$diag_bytes" in ''|*[!0-9]*) diag_status=1;; esac
            [ "$diag_status" = 0 ] && [ "$diag_bytes" -le 4096 ] || diag_status=1
        fi
    fi
    if [ "$diag_status" = 0 ]; then
        diag_line=$(printf 'LXBD1 %s %s %s' "$diag_boot_id" "$diag_uptime" "$diag_stage")
        diag_hash=$(printf '%s\n' "$diag_line" | $BB sha256sum) || diag_status=1
        diag_hash=${diag_hash%% *}
        [ "${#diag_hash}" = 64 ] || diag_status=1
    fi
    if [ "$diag_status" = 0 ]; then
        printf '%s %s\n' "$diag_line" "$diag_hash" >> "$diag_file" || diag_status=1
        $BB sync -f "$diag_file" || diag_status=1
    fi
    $BB umount "$diag_root" || diag_status=1
    $BB rmdir "$diag_root" || diag_status=1
    [ "$diag_status" = 0 ]
}
( $BB sleep 420; log 'V40_OUTER_DEADLINE_POWER_OFF';
  $BB poweroff -f; /bin/boot-proof-reboot ) \
    >/run/lynx/v40-outer-timer.log 2>&1 </dev/null &
v40_outer_timer=$!
printf '%s\n' "$v40_outer_timer" > /run/lynx/v40-outer-timer.pid || stop
lynx_bootdiag_append START || {
    log 'V40_START_RECORD_FAILED; POWER_OFF_REQUESTED'
    $BB poweroff -f
    /bin/boot-proof-reboot
    stop
}
lynx_wifi_local_supervise || {
    lynx_bootdiag_append WIFI_FAILED || log 'V40_WIFI_FAILED_RECORD_FAILED'
    log 'V40_WIFI_FAILED; POWER_OFF_REQUESTED'
    $BB poweroff -f
    /bin/boot-proof-reboot
    stop
}
lynx_bootdiag_append WIFI_READY || {
    log 'V40_WIFI_READY_RECORD_FAILED; POWER_OFF_REQUESTED'
    $BB poweroff -f
    /bin/boot-proof-reboot
    stop
}
log 'V40_WIFI_READY; HEALTH_DELAYED_UNTIL_UPTIME_190'
v40_at_120=0 v40_at_150=0 v40_at_180=0
while :; do
    IFS=' ' read -r v40_uptime v40_unused < /proc/uptime || stop
    v40_uptime=${v40_uptime%%.*}
    case "$v40_uptime" in ''|*[!0-9]*) stop;; esac
    if [ "$v40_at_120" = 0 ] && [ "$v40_uptime" -ge 120 ]; then
        lynx_bootdiag_append UPTIME_120 || stop
        v40_at_120=1
    fi
    if [ "$v40_at_150" = 0 ] && [ "$v40_uptime" -ge 150 ]; then
        lynx_bootdiag_append UPTIME_150 || stop
        v40_at_150=1
    fi
    if [ "$v40_at_180" = 0 ] && [ "$v40_uptime" -ge 180 ]; then
        lynx_bootdiag_append UPTIME_180 || stop
        v40_at_180=1
    fi
    [ "$v40_uptime" -lt 190 ] || break
    v40_supplies=0
    for v40_supply in /sys/class/power_supply/*; do
        [ -r "$v40_supply/online" ] || continue
        IFS= read -r v40_online < "$v40_supply/online" || stop
        [ "$v40_online" = 0 ] || {
            lynx_bootdiag_append CHARGER_ON || true
            log 'V40_CHARGER_ONLINE; POWER_OFF_REQUESTED'
            $BB poweroff -f
            /bin/boot-proof-reboot
            stop
        }
        v40_supplies=$((v40_supplies+1))
    done
    [ "$v40_supplies" -ge 1 ] || stop
    $BB sleep 5
done
lynx_bootdiag_append HEALTH_BEGIN || {
    log 'V40_HEALTH_BEGIN_RECORD_FAILED; POWER_OFF_REQUESTED'
    $BB poweroff -f
    /bin/boot-proof-reboot
    stop
}
log 'V40_HEALTH_BEGIN'
(
    while :; do
        v40_guard_count=0
        v40_guard_ok=1
        for v40_guard_supply in /sys/class/power_supply/*; do
            [ -r "$v40_guard_supply/online" ] || continue
            IFS= read -r v40_guard_online < "$v40_guard_supply/online" || {
                v40_guard_ok=0
                break
            }
            [ "$v40_guard_online" = 0 ] || {
                v40_guard_ok=0
                break
            }
            v40_guard_count=$((v40_guard_count+1))
        done
        [ "$v40_guard_count" -ge 1 ] && [ "$v40_guard_ok" = 1 ] || {
            log 'V40_CHARGER_GUARD_POWER_OFF'
            $BB poweroff -f
            /bin/boot-proof-reboot
        }
        $BB sleep 5
    done
) >/run/lynx/v40-charger-guard.log 2>&1 </dev/null &
v40_charger_guard=$!
printf '%s\n' "$v40_charger_guard" > /run/lynx/v40-charger-guard.pid || stop
v40_token=$($BB cat /etc/lynx/session-token) || stop
[ -n "$v40_token" ] || stop
printf '%s\n' "$v40_token" > /run/lynx/local-boot-ready.tmp || stop
$BB mv /run/lynx/local-boot-ready.tmp /run/lynx/local-boot-ready || stop
. /etc/lynx/autonomous-health-local-handoff.sh || stop
lynx_autonomous_health_local_handoff || {
    case "${LYNX_LOCAL_HEALTH_FAILURE:-}" in
        precheck) v40_reason=HEALTH_FAIL_PRECHECK ;;
        child) v40_reason=HEALTH_FAIL_CHILD ;;
        watcher) v40_reason=HEALTH_FAIL_WATCHER ;;
        battery) v40_reason=HEALTH_FAIL_BATTERY ;;
        thermal) v40_reason=HEALTH_FAIL_THERMAL ;;
        postcheck) v40_reason=HEALTH_FAIL_POSTCHECK ;;
        log) v40_reason=HEALTH_FAIL_LOG ;;
        *) v40_reason=HEALTH_FAILED ;;
    esac
    lynx_bootdiag_append "$v40_reason" || log 'V40_HEALTH_REASON_RECORD_FAILED'
    log "V40_HEALTH_FAILED reason=$v40_reason; POWER_OFF_REQUESTED"
    $BB poweroff -f
    /bin/boot-proof-reboot
    stop
}
[ -f /run/lynx/health-bootstrap/ready ] || stop
lynx_bootdiag_append HEALTH_READY || {
    log 'V40_HEALTH_READY_RECORD_FAILED; POWER_OFF_REQUESTED'
    $BB poweroff -f
    /bin/boot-proof-reboot
    stop
}
log 'V40_HEALTH_READY; BUSYBOX_PID1_OBSERVATION_WINDOW'
while :; do
    IFS=' ' read -r v40_uptime v40_unused < /proc/uptime || stop
    v40_uptime=${v40_uptime%%.*}
    case "$v40_uptime" in ''|*[!0-9]*) stop;; esac
    [ "$v40_uptime" -lt 300 ] || break
    $BB sh /run/lynx/lynx-health-supervisor.sh --once || {
        log 'V40_HEALTH_POSTCHECK_FAILED; POWER_OFF_REQUESTED'
        $BB poweroff -f
        /bin/boot-proof-reboot
        stop
    }
    $BB sleep 5
done
lynx_bootdiag_append END || log 'V40_END_RECORD_FAILED'
log 'V40_OBSERVATION_COMPLETE; POWER_OFF_REQUESTED'
$BB poweroff -f
/bin/boot-proof-reboot
stop
