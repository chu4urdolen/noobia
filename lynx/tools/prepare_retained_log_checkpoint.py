"""Prepare bounded retained-log query; no UFS/radio/storage driver activation."""
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port'
source=(P/'lynx-power-snapshot-v2-runtime.sh').read_text()
start=source.index('lynx_power_snapshot() {');end=source.index('lynx_module_progress() {',start)
query=r'''lynx_log_record_mask() {
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
'''.replace(r'\"','"')
source=source[:start]+query+source[end:]
source=source.replace('lynx_progress_write 32','lynx_progress_write 64').replace('lynx_progress_write "$((32+progress_index))"','lynx_progress_write 66').replace('lynx_progress_write 67','lynx_progress_write 65')
out=P/'lynx-retained-log-runtime.sh';assert not out.exists();out.write_text(source)
print('Bounded log query prepared; no phone contacted.')
