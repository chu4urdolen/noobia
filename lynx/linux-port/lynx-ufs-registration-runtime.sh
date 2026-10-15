# Proven first forty modules, followed by guarded original UFS registration.
# Codes: 0 returned, 1 guard refused, 2 UFS insertion failed,
# 3 still pending, 4 prefix insertion failed, 5 invalid/missing worker state.
lynx_ufs_registration_clock() {
    IFS=' ' read -r ufs_uptime ufs_unused < /proc/uptime || return 1
    ufs_seconds=${ufs_uptime%%.*}
    case "$ufs_seconds" in ''|*[!0-9]*) return 1 ;; esac
}
lynx_ufs_registration_state() {
    printf '%s\n' "$1" > /run/lynx/ufs-registration.tmp || return 1
    $BB mv /run/lynx/ufs-registration.tmp /run/lynx/ufs-registration || return 1
    if [ "${ufs_diag_ready:-0}" = 1 ]; then lynx_diag_emit 513 "$1" || true; fi
}
lynx_ufs_registration() {
    lynx_ufs_registration_clock || return 1
    ufs_started=$ufs_seconds
    (
        ufs_diag_ready=0
        if lynx_diag_init bootstrap; then ufs_diag_ready=1; fi
        lynx_ufs_registration_state 3 || exit 1
        ufs_index=0
        while IFS= read -r ufs_module; do
            [ -n "$ufs_module" ] || continue
            ufs_index=$((ufs_index+1))
            [ "$ufs_index" -le 40 ] || exit 1
            case "$ufs_module" in ''|*[!a-zA-Z0-9_.-]*) exit 1 ;; esac
            log "UFS_REGISTRATION_PREFIX_BEGIN index=$ufs_index module=$ufs_module"
            if ! $BB insmod "/lib/modules/$ufs_module"; then
                lynx_ufs_registration_state 4
                exit 1
            fi
        done < /etc/lynx/progress-modules.load
        [ "$ufs_index" = 40 ] || exit 1
        if ! lynx_ufs_registration_guard; then
            lynx_ufs_registration_state 1
            exit 1
        fi
        log 'UFS_REGISTRATION_STOCK_MODULE_BEGIN'
        if $BB insmod /lib/modules/ufs-mediatek-mod.ko; then
            lynx_ufs_registration_state 0 || exit 1
            log 'UFS_REGISTRATION_INSERTION_RETURNED; HARDWARE_PROBE_BLOCKED'
        else
            lynx_ufs_registration_state 2
            exit 1
        fi
    ) >> /run/lynx/boot.log 2>&1 &
    while :; do
        lynx_ufs_registration_clock || return 1
        [ "$ufs_seconds" -ge "$((ufs_started+90))" ] && break
        $BB sleep 1
    done
    ufs_code=5
    if IFS=' ' read -r ufs_code < /run/lynx/ufs-registration; then
        case "$ufs_code" in 0|1|2|3|4) ;; *) ufs_code=5 ;; esac
    else ufs_code=5; fi
    ufs_delay=$((120+5*ufs_code))
    log "UFS_REGISTRATION_FIELD code=$ufs_code target_delay=$ufs_delay"
    while :; do
        lynx_ufs_registration_clock || return 1
        [ "$ufs_seconds" -ge "$((ufs_started+ufs_delay))" ] && break
        $BB sleep 1
    done
    log 'UFS_REGISTRATION_REQUESTING_ONE_SUPPORTED_BOOTLOADER_REBOOT'
    /bin/boot-proof-reboot
    log 'UFS_REGISTRATION_REBOOT_RETURNED; NO_RETRY'
    return 1
}
