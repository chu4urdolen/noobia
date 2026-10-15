"""Prepare bounded retained trace parser; no phone access or new UFS activation."""
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port'
def main():
    source=(P/'lynx-retained-stage-runtime.sh').read_text()
    source=source.replace('    log_record_last_status=\n', '    log_record_last_status=\n    log_record_last_trace=\n')
    source=source.replace('[ "$log_stage" = 0200 ]','[ "$log_stage" = 0203 ]').replace('[ "$log_decimal" -gt 127 ] || log_record_last_status=$log_decimal','case "$log_decimal" in 16|17|18) log_record_last_status=$log_decimal ;; esac')
    marker='    if $BB grep -aEq \'Kernel panic'
    position=source.index(marker)
    source=source[:position]+'''    log_record_last_trace=$($BB grep -aEo "lx${log_reference}_[1-9]: \\(" "$log_capture" | $BB tail -n 1)
    if [ -n "$log_record_last_trace" ]; then
        log_record_last_trace=${log_record_last_trace#lx${log_reference}_}
        log_record_last_trace=${log_record_last_trace%%:*}
    fi
'''+source[position:]
    source=source.replace('    snapshot_last_status=\n', '    snapshot_last_status=\n    snapshot_last_trace=\n')
    source=source.replace('        # Keep one selected record;', '        if [ "$((log_record_mask&4))" != 0 ] && [ -n "$log_record_last_trace" ]; then log_priority=5; fi\n        # Keep one selected record;')
    source=source.replace('            snapshot_last_status=$log_record_last_status','            snapshot_last_status=$log_record_last_status\n            snapshot_last_trace=$log_record_last_trace')
    start=source.index('    snapshot_mask=0\n    if [ -n "$snapshot_last_status" ]')
    end=source.index('\n}',start)
    source=source[:start]+'''    selected_valid=$((snapshot_mask&4))
    snapshot_mask=0
    if [ "$selected_valid" != 0 ]; then
        if [ -n "$snapshot_last_trace" ]; then
            snapshot_mask=$snapshot_last_trace
        else
            case "$snapshot_last_status" in
                16) snapshot_mask=10 ;;
                17) snapshot_mask=11 ;;
                18) snapshot_mask=12 ;;
                *) snapshot_mask=13 ;;
            esac
        fi
    fi
    log "RETAINED_UFS_TRACE field=$snapshot_mask phase=$snapshot_last_status last_entry=$snapshot_last_trace; ONE_BOUNDED_RECORD_NOT_RETURN_PROOF"
'''+source[end:]
    source=source.replace('lynx_progress_write 126','lynx_progress_write 14').replace('lynx_progress_write 127','lynx_progress_write 15').replace('lynx_progress_write 128','lynx_progress_write 16').replace('snapshot_mask=129','snapshot_mask=17').replace('progress_code=130','progress_code=18').replace('progress_code=129','progress_code=17').replace('"$progress_code" -le 130','"$progress_code" -le 18')
    path=P/'lynx-retained-ufs-trace-runtime.sh';assert not path.exists();path.write_text(source)
    print('Read-only retained UFS trace query runtime prepared; no phone contacted.')
if __name__=='__main__':main()
