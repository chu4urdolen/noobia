# Clock registration checkpoint only: no scpsys, UFS, radio or network startup.
# Every module is named before insertion; state is stored atomically in RAM.
lynx_progress_clock() {
    IFS=' ' read -r progress_uptime progress_unused < /proc/uptime || return 1
    progress_seconds=${progress_uptime%%.*}
    case "$progress_seconds" in ''|*[!0-9]*) return 1 ;; esac
}
lynx_progress_write() {
    printf '%s\n' "$1" > /run/lynx/module-progress.tmp || return 1
    $BB mv /run/lynx/module-progress.tmp /run/lynx/module-progress || return 1
    if [ "${progress_diag_ready:-0}" = 1 ]; then lynx_diag_emit 512 "$1" || true; fi
    return 0
}
lynx_module_progress() {
    IFS=' ' read -r progress_expected < /etc/lynx/progress-count || return 1
    case "$progress_expected" in 0|28|29|30|31|32|34) ;; *) return 1 ;; esac
    lynx_progress_clock || return 1
    progress_started=$progress_seconds
    (
        progress_diag_ready=0
        if lynx_diag_init bootstrap; then progress_diag_ready=1; fi
        progress_index=0
        while IFS= read -r progress_module; do
            [ -n "$progress_module" ] || continue
            progress_index=$((progress_index+1))
            [ "$progress_index" -le "$progress_expected" ] || exit 1
            case "$progress_module" in ''|*[!a-zA-Z0-9_.-]*) exit 1 ;; esac
            lynx_progress_write "$progress_index" || exit 1
            log "PROGRESS_MODULE_BEGIN index=$progress_index module=$progress_module"
            if $BB insmod "/lib/modules/$progress_module"; then
                lynx_progress_write "$((progress_index+40))" || exit 1
            else
                lynx_progress_write "$((progress_index+80))" || exit 1
                log "PROGRESS_MODULE_INSERTION_FAILED index=$progress_index module=$progress_module"
                exit 1
            fi
        done < /etc/lynx/progress-modules.load
        [ "$progress_index" = "$progress_expected" ] || exit 1
        lynx_progress_write 0 || exit 1
        log 'PROGRESS_SELECTED_PREFIX_INSERTIONS_COMPLETED; BINDING_NOT_PROVEN'
    ) >> /run/lynx/boot.log 2>&1 &
    progress_worker=$!
    # Fixed sampling time makes a still-running insertion visible without
    # reading driver controls, waiting on insmod, or killing the worker.
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
    log 'MODULE_PROGRESS_REQUESTING_ONE_SUPPORTED_BOOTLOADER_REBOOT'
    /bin/boot-proof-reboot
    log 'MODULE_PROGRESS_REBOOT_RETURNED; NO_RETRY'
    return 1
}
