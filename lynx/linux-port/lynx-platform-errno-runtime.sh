# Seven-bit timing field, with explicit sentinels and exactly one normal reboot.
lynx_storage_probe_clock() {
    IFS=' ' read -r probe_uptime probe_unused < /proc/uptime || return 1
    probe_seconds=${probe_uptime%%.*}
    case "$probe_seconds" in ''|*[!0-9]*) return 1 ;; esac
}
lynx_storage_probe() {
    lynx_storage_probe_clock || return 1
    probe_started=$probe_seconds
    (
        trace_ready=0
        if lynx_driver_trace_setup; then trace_ready=1; fi
        lynx_wifi_bootstrap_child
        probe_status=$?
        probe_code=126
        if [ "$trace_ready" = 1 ] && lynx_driver_trace_capture; then
            trace_expected_pid=$($BB cat /run/lynx/trace-health-pid)
            if lynx_live_ufs_name; then
                printf '%s\n' "$live_ufs_name" > /run/lynx/ufs-live-name
                if $BB awk -v expected_pid="$trace_expected_pid" -v expected_device="$live_ufs_name" -f /etc/lynx/classify-driver-trace.awk /run/lynx/driver-trace.log > /run/lynx/driver-trace-result; then
                    if IFS=' ' read -r probe_code trace_platform_ret trace_count trace_health < /run/lynx/driver-trace-result; then
                        case "$probe_code" in ''|*[!0-9]*) probe_code=126 ;; esac
                        [ "$probe_code" -le 127 ] || probe_code=126
                        log "PLATFORM_ERRNO_FIELD code=$probe_code retval=$trace_platform_ret count=$trace_count health=$trace_health name=$live_ufs_name"
                    fi
                fi
            else probe_code=124; fi
        fi
        printf '%s %s\n' "$probe_code" "$probe_status" > /run/lynx/storage-outcome.tmp
        $BB mv /run/lynx/storage-outcome.tmp /run/lynx/storage-outcome
    ) >> /run/lynx/boot.log 2>&1 &
    while :; do
        if [ -f /run/lynx/storage-outcome ]; then
            IFS=' ' read -r probe_code probe_status < /run/lynx/storage-outcome || return 1
            case "$probe_code" in ''|*[!0-9]*) return 1 ;; esac
            [ "$probe_code" -le 127 ] || return 1
            case "$probe_status" in ''|*[!0-9]*) return 1 ;; esac
            break
        fi
        lynx_storage_probe_clock || return 1
        if [ "$probe_seconds" -ge "$((probe_started+180))" ]; then
            probe_code=127;probe_status=65535;break
        fi
        $BB sleep 1
    done
    probe_delay=$((60+2*probe_code))
    log "ERRNO_FIELD code=$probe_code status=$probe_status target_delay=$probe_delay"
    [ "${diag_ready:-0}" != 1 ] || lynx_diag_emit 253 "$probe_code"
    while :; do
        lynx_storage_probe_clock || return 1
        [ "$probe_seconds" -ge "$((probe_started+probe_delay))" ] && break
        $BB sleep 1
    done
    log 'ERRNO_FIELD_REQUESTING_ONE_SUPPORTED_BOOTLOADER_REBOOT'
    /bin/boot-proof-reboot
    log 'ERRNO_FIELD_REBOOT_RETURNED; NO_RETRY'
    return 1
}
