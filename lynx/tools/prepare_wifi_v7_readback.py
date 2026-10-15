"""Prepare a separately named bounded Wi-Fi v7 retained failure query."""
import json
from pathlib import Path
R=Path(__file__).resolve().parent.parent;P=R/'linux-port';T=R/'tools'
def save(path, text):
    assert not path.exists(),path
    path.write_text(text)
def main():
    source=(P/'lynx-retained-ufs-trace-runtime.sh').read_text()
    start=source.index('lynx_log_record_mask() {');end=source.index('lynx_module_progress() {')
    replacement=r'''lynx_log_record_mask() {
    log_record_code=0
    log_record_priority=0
    $BB grep -aEo 'LXDG1 [0-9a-f]{32} [0-9a-f]{8} [0-9a-f]{8} [0-9a-f]{4} [0-9a-f]{4} [0-9a-f]{64}' "$log_capture" > /run/lynx/retained-capsules
    while IFS=' ' read -r log_magic log_token log_seq log_uptime_hex log_stage log_status log_hash log_extra; do
        [ "$log_token" = "$log_reference" ] && [ -z "$log_extra" ] || continue
        log_payload=$(printf '%s %s %s %s %s %s' "$log_magic" "$log_token" "$log_seq" "$log_uptime_hex" "$log_stage" "$log_status") || continue
        log_actual=$(printf '%s' "$log_payload" | $BB sha256sum) || continue
        log_actual=${log_actual%% *}
        [ "$log_actual" = "$log_hash" ] || continue
        log_code=13
        log_priority=1
        case "$log_stage" in
            00fe)
                log_priority=3
                case "$log_status" in
                    0097) log_code=1 ;; 0098) log_code=2 ;;
                    0099) log_code=3 ;; 009a) log_code=4 ;;
                    *) log_code=5 ;;
                esac ;;
            00ff) log_priority=3; log_code=6 ;;
            0010) log_priority=2; log_code=7 ;;
            0011|0203|0204|1021|1022|1023|1024|1025|1026|1027)
                log_priority=2; log_code=8 ;;
            0012) log_priority=2; log_code=9 ;;
            0013) log_priority=2; log_code=10 ;;
            0014|0020) log_priority=2; log_code=11 ;;
            0021|0022|0023|0024) log_priority=2; log_code=12 ;;
            0025|0026|0027|0028) log_priority=2; log_code=13 ;;
        esac
        # Latest sampled byte order within a priority, not numerical sequence.
        # Reset/module chatter must not hide a preceding failure capsule.
        if [ "$log_priority" -ge "$log_record_priority" ]; then
            log_record_priority=$log_priority
            log_record_code=$log_code
        fi
    done < /run/lynx/retained-capsules
}
lynx_power_snapshot() {
    snapshot_mask=0
    log_best_priority=0
    log_reference=$($BB cat /etc/lynx/reference-ufs-token) || { snapshot_mask=17; return 1; }
    case "$log_reference" in ''|*[!0-9a-f]*) snapshot_mask=17; return 1 ;; esac
    [ "${#log_reference}" = 32 ] || { snapshot_mask=17; return 1; }
    $BB mkdir -p /run/lynx/retained || { snapshot_mask=17; return 1; }
    log_index=0
    for log_source in /sys/fs/pstore/* /proc/last_kmsg; do
        [ -f "$log_source" ] && [ ! -L "$log_source" ] || continue
        log_index=$((log_index+1))
        [ "$log_index" -le 8 ] || break
        log_capture=/run/lynx/retained/record-$log_index
        $BB head -c 1048576 "$log_source" > "$log_capture"
        [ -s "$log_capture" ] || continue
        lynx_log_record_mask
        # First of tied files: no cross-file merging or newest-boot assertion.
        if [ "$log_record_priority" -gt "$log_best_priority" ]; then
            snapshot_mask=$log_record_code
            log_best_priority=$log_record_priority
            printf '%s\n' "$log_source" > /run/lynx/retained/selected-source
        fi
    done
    log "RETAINED_WIFI_FAILURE field=$snapshot_mask; ONE_BOUNDED_RECORD_CHECKSUM_NOT_COMPLETE_STREAM"
}
'''
    source=source[:start]+replacement+source[end:]
    runtime=P/'lynx-retained-wifi-v7-runtime.sh';save(runtime,source)
    builder=(P/'prepare_retained_refclk_trace_image.py').read_text()
    builder=builder.replace('busybox-retained-refclk-trace-query-v1','busybox-retained-wifi-v7-query-v1').replace('lynx-retained-ufs-trace-runtime.sh',runtime.name).replace('busybox-refclk-trace-probe-v2','busybox-wifi-ssh-twostage-v7').replace('b4a505426c91b3a0c151b977ddcfbfddeabcca612a59959408230c19d317aea1','9a17b8e72e8e8fe8928f551fcf593cee1d19a712affe498f23f637e7ac4da00c')
    start=builder.index("    codes={'0':");end=builder.index('    report=',start)
    codes={'0':'no checksum-valid Wi-Fi v7 reference capsule in selected bounded record',
        '1':'bootstrap failed: base drivers (151)', '2':'bootstrap failed: storage drivers or guards (152)',
        '3':'bootstrap failed: partition discovery (153)', '4':'bootstrap failed: own boot_a payload read/verification/extraction (154)',
        '5':'bootstrap failed: other status', '6':'Wi-Fi worker failed: status not retrieved',
        '7':'last retained major phase: base drivers', '8':'last retained major phase: storage or UFS clock/probe',
        '9':'last retained major phase: partition discovery', '10':'last retained major phase: own boot_a payload',
        '11':'last retained major phase: payload extracted or factory calibration', '12':'last retained major phase: radio initialization',
        '13':'reference capsule retained; network phase or no recognized failure/major phase',
        '14':'base prefix pending','15':'retained query pending','16':'base insertion failed','17':'reference or progress malformed','18':'worker state unavailable'}
    builder=builder[:start]+'    codes='+repr(codes)+'\n'+builder[end:]
    save(P/'prepare_retained_wifi_v7_image.py',builder)
    (P/'docs/retained-wifi-v7-codebook.json').write_text(json.dumps(codes,indent=2)+'\n')
    print('Separate readback runtime and builder prepared; no phone contacted.')
if __name__=='__main__': main()
