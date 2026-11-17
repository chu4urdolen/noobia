. /etc/lynx/wifi-runtime.sh || stop
. /etc/lynx/wifi-local-supervise.sh || stop
# V39 diagnostic only. Retain V38's proven Wi-Fi window, then exercise the
# existing health startup once. No Alpine handoff; V33 remains rollback.
lynx_bootdiag_append() {
    diag_stage=$1
    case "$diag_stage" in
        START|WIFI_READY|WIFI_FAILED|UPTIME_120|UPTIME_150|UPTIME_180|HEALTH_BEGIN|HEALTH_FAILED|HEALTH_READY|CHARGER_ON|END) ;;
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
( $BB sleep 420; log 'V39_OUTER_DEADLINE_POWER_OFF';
  $BB poweroff -f; /bin/boot-proof-reboot ) \
    >/run/lynx/v39-outer-timer.log 2>&1 </dev/null &
v39_outer_timer=$!
printf '%s\n' "$v39_outer_timer" > /run/lynx/v39-outer-timer.pid || stop
lynx_bootdiag_append START || {
    log 'V39_START_RECORD_FAILED; POWER_OFF_REQUESTED'
    $BB poweroff -f
    /bin/boot-proof-reboot
    stop
}
lynx_wifi_local_supervise || {
    lynx_bootdiag_append WIFI_FAILED || log 'V39_WIFI_FAILED_RECORD_FAILED'
    log 'V39_WIFI_FAILED; POWER_OFF_REQUESTED'
    $BB poweroff -f
    /bin/boot-proof-reboot
    stop
}
lynx_bootdiag_append WIFI_READY || {
    log 'V39_WIFI_READY_RECORD_FAILED; POWER_OFF_REQUESTED'
    $BB poweroff -f
    /bin/boot-proof-reboot
    stop
}
log 'V39_WIFI_READY; HEALTH_DELAYED_UNTIL_UPTIME_190'
v39_at_120=0 v39_at_150=0 v39_at_180=0
while :; do
    IFS=' ' read -r v39_uptime v39_unused < /proc/uptime || stop
    v39_uptime=${v39_uptime%%.*}
    case "$v39_uptime" in ''|*[!0-9]*) stop;; esac
    if [ "$v39_at_120" = 0 ] && [ "$v39_uptime" -ge 120 ]; then
        lynx_bootdiag_append UPTIME_120 || stop
        v39_at_120=1
    fi
    if [ "$v39_at_150" = 0 ] && [ "$v39_uptime" -ge 150 ]; then
        lynx_bootdiag_append UPTIME_150 || stop
        v39_at_150=1
    fi
    if [ "$v39_at_180" = 0 ] && [ "$v39_uptime" -ge 180 ]; then
        lynx_bootdiag_append UPTIME_180 || stop
        v39_at_180=1
    fi
    [ "$v39_uptime" -lt 190 ] || break
    v39_supplies=0
    for v39_supply in /sys/class/power_supply/*; do
        [ -r "$v39_supply/online" ] || continue
        IFS= read -r v39_online < "$v39_supply/online" || stop
        [ "$v39_online" = 0 ] || {
            lynx_bootdiag_append CHARGER_ON || true
            log 'V39_CHARGER_ONLINE; POWER_OFF_REQUESTED'
            $BB poweroff -f
            /bin/boot-proof-reboot
            stop
        }
        v39_supplies=$((v39_supplies+1))
    done
    [ "$v39_supplies" -ge 1 ] || stop
    $BB sleep 5
done
lynx_bootdiag_append HEALTH_BEGIN || {
    log 'V39_HEALTH_BEGIN_RECORD_FAILED; POWER_OFF_REQUESTED'
    $BB poweroff -f
    /bin/boot-proof-reboot
    stop
}
log 'V39_HEALTH_BEGIN'
# Charging is still unvalidated under native Linux. Keep a separate guard
# alive even if the health child stalls inside a module probe.
(
    while :; do
        v39_guard_count=0
        v39_guard_ok=1
        for v39_guard_supply in /sys/class/power_supply/*; do
            [ -r "$v39_guard_supply/online" ] || continue
            IFS= read -r v39_guard_online < "$v39_guard_supply/online" || {
                v39_guard_ok=0
                break
            }
            [ "$v39_guard_online" = 0 ] || {
                v39_guard_ok=0
                break
            }
            v39_guard_count=$((v39_guard_count+1))
        done
        [ "$v39_guard_count" -ge 1 ] && [ "$v39_guard_ok" = 1 ] || {
            log 'V39_CHARGER_GUARD_POWER_OFF'
            $BB poweroff -f
            /bin/boot-proof-reboot
        }
        $BB sleep 5
    done
) >/run/lynx/v39-charger-guard.log 2>&1 </dev/null &
v39_charger_guard=$!
printf '%s\n' "$v39_charger_guard" > /run/lynx/v39-charger-guard.pid || stop
v39_token=$($BB cat /etc/lynx/session-token) || stop
[ -n "$v39_token" ] || stop
printf '%s\n' "$v39_token" > /run/lynx/local-boot-ready.tmp || stop
$BB mv /run/lynx/local-boot-ready.tmp /run/lynx/local-boot-ready || stop
. /etc/lynx/autonomous-health-local-handoff.sh || stop
lynx_autonomous_health_local_handoff || {
    lynx_bootdiag_append HEALTH_FAILED || log 'V39_HEALTH_FAILED_RECORD_FAILED'
    log 'V39_HEALTH_FAILED; POWER_OFF_REQUESTED'
    $BB poweroff -f
    /bin/boot-proof-reboot
    stop
}
[ -f /run/lynx/health-bootstrap/ready ] || stop
lynx_bootdiag_append HEALTH_READY || {
    log 'V39_HEALTH_READY_RECORD_FAILED; POWER_OFF_REQUESTED'
    $BB poweroff -f
    /bin/boot-proof-reboot
    stop
}
log 'V39_HEALTH_READY; BUSYBOX_PID1_OBSERVATION_WINDOW'
while :; do
    IFS=' ' read -r v39_uptime v39_unused < /proc/uptime || stop
    v39_uptime=${v39_uptime%%.*}
    case "$v39_uptime" in ''|*[!0-9]*) stop;; esac
    [ "$v39_uptime" -lt 300 ] || break
    $BB sh /run/lynx/lynx-health-supervisor.sh --once || {
        log 'V39_HEALTH_POSTCHECK_FAILED; POWER_OFF_REQUESTED'
        $BB poweroff -f
        /bin/boot-proof-reboot
        stop
    }
    $BB sleep 5
done
lynx_bootdiag_append END || log 'V39_END_RECORD_FAILED'
log 'V39_OBSERVATION_COMPLETE; POWER_OFF_REQUESTED'
$BB poweroff -f
/bin/boot-proof-reboot
stop
