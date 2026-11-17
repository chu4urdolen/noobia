# Read-only controller/domain metadata after the proven34-module prefix.
# No UFS controller, PHY, block device, firmware/calibration or emergency reset.
lynx_progress_clock() {
    IFS=' ' read -r progress_uptime progress_unused < /proc/uptime || return 1
    progress_seconds=${progress_uptime%%.*}
    case "$progress_seconds" in ''|*[!0-9]*) return 1 ;; esac
}
lynx_progress_write() {
    printf '%s\n' "$1" > /run/lynx/module-progress.tmp || return 1
    $BB mv /run/lynx/module-progress.tmp /run/lynx/module-progress || return 1
    if [ "${progress_diag_ready:-0}" = 1 ]; then lynx_diag_emit 512 "$1" || true; fi
}
lynx_power_snapshot() {
    snapshot_mask=0
    for snapshot_device in /sys/bus/platform/drivers/mtk-scpsys-mt6983/*; do
        case "${snapshot_device##*/}" in *1c001000*)
            [ ! -L "$snapshot_device" ] || snapshot_mask=$((snapshot_mask|1)) ;;
        esac
    done
    snapshot_debugfs=0
    while IFS=' ' read -r snapshot_dev snapshot_point snapshot_type snapshot_rest; do
        if [ "$snapshot_point" = /sys/kernel/debug ] && [ "$snapshot_type" = debugfs ]; then snapshot_debugfs=1; fi
    done < /proc/mounts
    if [ "$snapshot_debugfs" = 0 ]; then
        if $BB mount -t debugfs debugfs /sys/kernel/debug; then snapshot_debugfs=1; fi
    fi
    if [ "$snapshot_debugfs" = 1 ]; then
        snapshot_mask=$((snapshot_mask|4))
        [ ! -d /sys/kernel/debug/pm_genpd/ufs0 ] || snapshot_mask=$((snapshot_mask|2))
    fi
    [ ! -w /proc/sysrq-trigger ] || snapshot_mask=$((snapshot_mask|8))
    log "POWER_METADATA_SNAPSHOT mask=$snapshot_mask; NO_POWER_CONTROL_READ"
}
lynx_module_progress() {
    IFS=' ' read -r progress_expected < /etc/lynx/progress-count || return 1
    [ "$progress_expected" = 34 ] || return 1
    lynx_progress_clock || return 1
    progress_started=$progress_seconds
    (
        progress_diag_ready=0
        if lynx_diag_init bootstrap; then progress_diag_ready=1; fi
        lynx_progress_write 17 || exit 1
        progress_index=0
        while IFS= read -r progress_module; do
            [ -n "$progress_module" ] || continue
            progress_index=$((progress_index+1))
            [ "$progress_index" -le 34 ] || exit 1
            case "$progress_module" in *[!a-zA-Z0-9_.-]*) exit 1 ;; esac
            log "POWER_SNAPSHOT_MODULE_BEGIN index=$progress_index module=$progress_module"
            if ! $BB insmod "/lib/modules/$progress_module"; then
                lynx_progress_write 16 || exit 1
                exit 1
            fi
        done < /etc/lynx/progress-modules.load
        [ "$progress_index" = 34 ] || exit 1
        lynx_progress_write 18 || exit 1
        lynx_power_snapshot
        lynx_progress_write "$snapshot_mask" || exit 1
    ) >> /run/lynx/boot.log 2>&1 &
    while :; do
        lynx_progress_clock || return 1
        [ "$progress_seconds" -ge "$((progress_started+90))" ] && break
        $BB sleep 1
    done
    progress_code=127
    if [ -f /run/lynx/module-progress ]; then
        if IFS=' ' read -r progress_code < /run/lynx/module-progress; then
            case "$progress_code" in ''|*[!0-9]*) progress_code=125 ;; esac
            [ "$progress_code" -le 127 ] || progress_code=125
        else progress_code=125; fi
    fi
    progress_delay=$((120+2*progress_code))
    log "MODULE_PROGRESS_FIELD code=$progress_code target_delay=$progress_delay"
    while :; do
        lynx_progress_clock || return 1
        [ "$progress_seconds" -ge "$((progress_started+progress_delay))" ] && break
        $BB sleep 1
    done
    /bin/boot-proof-reboot
    log 'POWER_SNAPSHOT_NORMAL_RESET_RETURNED; NO_RETRY'
    return 1
}
