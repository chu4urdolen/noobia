. /etc/lynx/wifi-runtime.sh || stop
. /etc/lynx/wifi-local-supervise.sh || stop
# V38 diagnostic only. One short ext4 mount per checksummed stage record;
# no Alpine handoff or health module load. V33 remains the rollback image.
lynx_bootdiag_append() {
    diag_stage=$1
    case "$diag_stage" in
        START|WIFI_READY|WIFI_FAILED|UPTIME_120|UPTIME_150|UPTIME_180|CHARGER_ON|END) ;;
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
( $BB sleep 230; log 'V38_OUTER_DEADLINE_POWER_OFF';
  $BB poweroff -f; /bin/boot-proof-reboot ) \
    >/run/lynx/v38-outer-timer.log 2>&1 </dev/null &
v38_outer_timer=$!
printf '%s\n' "$v38_outer_timer" > /run/lynx/v38-outer-timer.pid || stop
lynx_bootdiag_append START || {
    log 'V38_START_RECORD_FAILED; POWER_OFF_REQUESTED'
    $BB poweroff -f
    /bin/boot-proof-reboot
    stop
}
lynx_wifi_local_supervise || {
    lynx_bootdiag_append WIFI_FAILED || log 'V38_WIFI_FAILED_RECORD_FAILED'
    log 'V38_WIFI_FAILED; POWER_OFF_REQUESTED'
    $BB poweroff -f
    /bin/boot-proof-reboot
    stop
}
lynx_bootdiag_append WIFI_READY || {
    log 'V38_WIFI_READY_RECORD_FAILED; POWER_OFF_REQUESTED'
    $BB poweroff -f
    /bin/boot-proof-reboot
    stop
}
log 'V38_WIFI_READY; HEALTH_NOT_STARTED'
v38_at_120=0 v38_at_150=0 v38_at_180=0
while :; do
    IFS=' ' read -r v38_uptime v38_unused < /proc/uptime || stop
    v38_uptime=${v38_uptime%%.*}
    case "$v38_uptime" in ''|*[!0-9]*) stop;; esac
    if [ "$v38_at_120" = 0 ] && [ "$v38_uptime" -ge 120 ]; then
        lynx_bootdiag_append UPTIME_120 || stop
        v38_at_120=1
    fi
    if [ "$v38_at_150" = 0 ] && [ "$v38_uptime" -ge 150 ]; then
        lynx_bootdiag_append UPTIME_150 || stop
        v38_at_150=1
    fi
    if [ "$v38_at_180" = 0 ] && [ "$v38_uptime" -ge 180 ]; then
        lynx_bootdiag_append UPTIME_180 || stop
        v38_at_180=1
    fi
    [ "$v38_uptime" -lt 190 ] || break
    v38_supplies=0
    for v38_supply in /sys/class/power_supply/*; do
        [ -r "$v38_supply/online" ] || continue
        IFS= read -r v38_online < "$v38_supply/online" || stop
        [ "$v38_online" = 0 ] || {
            lynx_bootdiag_append CHARGER_ON || true
            log 'V38_CHARGER_ONLINE; POWER_OFF_REQUESTED'
            $BB poweroff -f
            /bin/boot-proof-reboot
            stop
        }
        v38_supplies=$((v38_supplies+1))
    done
    [ "$v38_supplies" -ge 1 ] || stop
    $BB sleep 5
done
lynx_bootdiag_append END || log 'V38_END_RECORD_FAILED'
log 'V38_OBSERVATION_COMPLETE; POWER_OFF_REQUESTED'
$BB poweroff -f
/bin/boot-proof-reboot
stop
