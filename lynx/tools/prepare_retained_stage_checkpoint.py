"""Query the last checksum-valid progress marker from the selected retained record."""
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port'
source=(P/'lynx-retained-log-runtime.sh').read_text()
source=source.replace('    log_record_mask=1','    log_record_mask=1\n    log_record_last_status=')
old='        [ "$log_actual" != "$log_hash" ] || log_record_mask=$((log_record_mask|4))'
new='''        if [ "$log_actual" = "$log_hash" ]; then
            log_record_mask=$((log_record_mask|4))
            if [ "$log_stage" = 0200 ]; then
                log_decimal=$((0x$log_status))
                [ "$log_decimal" -gt 127 ] || log_record_last_status=$log_decimal
            fi
        fi'''
assert old in source;source=source.replace(old,new)
source=source.replace('    log_best_priority=0','    log_best_priority=0\n    snapshot_last_status=')
source=source.replace('        # Keep one selected record;', '        [ -z "$log_record_last_status" ] || log_priority=4\n        # Keep one selected record;')
source=source.replace('            log_best_priority=$log_priority','            log_best_priority=$log_priority\n            snapshot_last_status=$log_record_last_status')
old='    log "RETAINED_LOG_SAMPLE mask=$snapshot_mask files_considered=$log_index; RAM_ONLY"'
new='''    snapshot_mask=0
    if [ -n "$snapshot_last_status" ]; then
        snapshot_mask=129
        while IFS=' ' read -r log_map_status log_map_code; do
            if [ "$log_map_status" = "$snapshot_last_status" ]; then snapshot_mask=$log_map_code; break; fi
        done < /etc/lynx/reference-progress-map
    fi
    log "RETAINED_PROGRESS_MARKER field=$snapshot_last_status transport=$snapshot_mask; CHECKSUM_NOT_COMPLETE_STREAM"
'''
assert old in source;source=source.replace(old,new)
source=source.replace('lynx_progress_write 64','lynx_progress_write 126').replace('lynx_progress_write 65','lynx_progress_write 127').replace('lynx_progress_write 66','lynx_progress_write 128').replace('snapshot_mask=68','snapshot_mask=129').replace('progress_code=69','progress_code=130').replace('progress_code=68','progress_code=129').replace('"$progress_code" -le 69','"$progress_code" -le 130')
out=P/'lynx-retained-stage-runtime.sh';assert not out.exists();out.write_text(source)
print('Verified retained-stage query prepared; no phone contacted.')
