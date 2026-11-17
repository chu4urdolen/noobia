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
lynx_log_record_mask() {
    log_record_mask=1
    if $BB grep -aFq "$log_reference" "$log_capture"; then log_record_mask=$((log_record_mask|2)); fi
    $BB grep -aEo 'LXDG1 [0-9a-f]{32} [0-9a-f]{8} [0-9a-f]{8} [0-9a-f]{4} [0-9a-f]{4} [0-9a-f]{64}' "$log_capture" > /run/lynx/retained-capsules
    while IFS=' ' read -r log_magic log_token log_seq log_uptime_hex log_stage log_status log_hash log_extra; do
        [ "$log_token" = "$log_reference" ] && [ -z "$log_extra" ] || continue
        log_payload=$(printf '%s %s %s %s %s %s' "$log_magic" "$log_token" "$log_seq" "$log_uptime_hex" "$log_stage" "$log_status") || continue
        log_actual=$(printf '%s' "$log_payload" | $BB sha256sum) || continue
        log_actual=${log_actual%% *}
        [ "$log_actual" != "$log_hash" ] || log_record_mask=$((log_record_mask|4))
    done < /run/lynx/retained-capsules
    if $BB grep -aEq 'Kernel panic - not syncing|Internal error:|BUG: unable to handle|Unable to handle kernel' "$log_capture"; then log_record_mask=$((log_record_mask|8)); fi
    if $BB grep -aFq 'CFI failure' "$log_capture"; then log_record_mask=$((log_record_mask|16)); fi
    log_trace=$($BB awk '/Call [Tt]race:/ { n=60; next } n>0 { if ($0 ~ /ufshcd|ufs_mtk|scpsys_power|genpd_power|arm_smccc_smc|__clk_enable/) found=1; n-- } END { print found+0 }' "$log_capture")
    [ "$log_trace" != 1 ] || log_record_mask=$((log_record_mask|32))
}
lynx_power_snapshot() {
    snapshot_mask=0
    log_best_priority=0
    log_reference=$($BB cat /etc/lynx/reference-ufs-token) || { snapshot_mask=68; return 1; }
    case "$log_reference" in ''|*[!0-9a-f]*) snapshot_mask=68; return 1 ;; esac
    [ "${#log_reference}" = 32 ] || { snapshot_mask=68; return 1; }
    $BB mkdir -p /run/lynx/retained || { snapshot_mask=68; return 1; }
    log_index=0
    for log_source in /sys/fs/pstore/* /proc/last_kmsg; do
        [ -f "$log_source" ] && [ ! -L "$log_source" ] || continue
        log_index=$((log_index+1))
        [ "$log_index" -le 8 ] || break
        log_capture=/run/lynx/retained/record-$log_index
        # Standard kernel file read, bounded to1MiB per file/8files. No raw RAM.
        $BB head -c 1048576 "$log_source" > "$log_capture"
        [ -s "$log_capture" ] || continue
        lynx_log_record_mask
        log_priority=1
        [ "$((log_record_mask&2))" = 0 ] || log_priority=2
        [ "$((log_record_mask&4))" = 0 ] || log_priority=3
        # Keep one selected record; never combine crash markers across files.
        if [ "$log_priority" -gt "$log_best_priority" ] || { [ "$log_priority" = "$log_best_priority" ] && [ "$log_record_mask" -gt "$snapshot_mask" ]; }; then
            snapshot_mask=$log_record_mask
            log_best_priority=$log_priority
            printf '%s\n' "$log_source" > /run/lynx/retained/selected-source
        fi
    done
    log "RETAINED_LOG_SAMPLE mask=$snapshot_mask files_considered=$log_index; RAM_ONLY"
}
lynx_module_progress() {
    IFS=' ' read -r progress_expected < /etc/lynx/progress-count || return 1
    [ "$progress_expected" = 34 ] || return 1
    lynx_progress_clock || return 1
    progress_started=$progress_seconds
    (
        progress_diag_ready=0
        if lynx_diag_init bootstrap; then progress_diag_ready=1; fi
        lynx_progress_write 64 || exit 1
        progress_index=0
        while IFS= read -r progress_module; do
            [ -n "$progress_module" ] || continue
            progress_index=$((progress_index+1))
            [ "$progress_index" -le 34 ] || exit 1
            case "$progress_module" in *[!a-zA-Z0-9_.-]*) exit 1 ;; esac
            log "POWER_SNAPSHOT_MODULE_BEGIN index=$progress_index module=$progress_module"
            if ! $BB insmod "/lib/modules/$progress_module"; then
                lynx_progress_write 66 || exit 1
                exit 1
            fi
        done < /etc/lynx/progress-modules.load
        [ "$progress_index" = 34 ] || exit 1
        lynx_progress_write 65 || exit 1
        lynx_power_snapshot
        lynx_progress_write "$snapshot_mask" || exit 1
    ) >> /run/lynx/boot.log 2>&1 &
    while :; do
        lynx_progress_clock || return 1
        [ "$progress_seconds" -ge "$((progress_started+90))" ] && break
        $BB sleep 1
    done
    progress_code=69
    if [ -f /run/lynx/module-progress ]; then
        if IFS=' ' read -r progress_code < /run/lynx/module-progress; then
            case "$progress_code" in ''|*[!0-9]*) progress_code=68 ;; esac
            [ "$progress_code" -le 69 ] || progress_code=68
        else progress_code=68; fi
    fi
    progress_delay=$((120+5*progress_code))
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
