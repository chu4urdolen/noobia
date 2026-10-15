# Coarse timing channel, not authenticated or persistent kernel log retrieval.
# Exactly one ordinary bootloader reboot; no new partition write operations.
lynx_storage_probe_clock() {
    IFS=' ' read -r probe_uptime probe_unused < /proc/uptime || return 1
    probe_seconds=${probe_uptime%%.*}
    case "$probe_seconds" in ''|*[!0-9]*) return 1 ;; esac
}
lynx_storage_probe() {
    lynx_storage_probe_clock || return 1
    probe_started=$probe_seconds
    (
        lynx_wifi_bootstrap_child
        probe_status=$?
        probe_code=8
        case "$probe_status" in
            0) probe_code=6 ;;
            151) probe_code=1 ;;
            152) probe_code=2 ;;
            153)
                probe_code=3
                # Only inspect driver symlinks; do not read hardware controls.
                for probe_device in /sys/bus/platform/devices/*; do
                    [ -L "$probe_device/driver" ] || continue
                    probe_driver=$($BB readlink "$probe_device/driver") || continue
                    case "$probe_driver" in */ufshcd-mtk) probe_code=4 ;; esac
                done
                ;;
            154) probe_code=5 ;;
        esac
        printf '%s %s\n' "$probe_code" "$probe_status" > /run/lynx/storage-outcome.tmp
        $BB mv /run/lynx/storage-outcome.tmp /run/lynx/storage-outcome
    ) >> /run/lynx/boot.log 2>&1 &
    while :; do
        if [ -f /run/lynx/storage-outcome ]; then
            IFS=' ' read -r probe_code probe_status < /run/lynx/storage-outcome || return 1
            case "$probe_code" in 1|2|3|4|5|6|8) ;; *) return 1 ;; esac
            case "$probe_status" in ''|*[!0-9]*) return 1 ;; esac
            break
        fi
        lynx_storage_probe_clock || return 1
        if [ "$probe_seconds" -ge "$((probe_started+180))" ]; then
            probe_code=7
            probe_status=65535
            break
        fi
        $BB sleep 1
    done
    probe_delay=$((40+25*probe_code))
    log "STORAGE_OUTCOME code=$probe_code status=$probe_status target_delay=$probe_delay"
    [ "${diag_ready:-0}" != 1 ] || lynx_diag_emit 253 "$probe_code"
    while :; do
        lynx_storage_probe_clock || return 1
        [ "$probe_seconds" -ge "$((probe_started+probe_delay))" ] && break
        $BB sleep 1
    done
    log 'STORAGE_OUTCOME_REQUESTING_ONE_SUPPORTED_BOOTLOADER_REBOOT'
    /bin/boot-proof-reboot
    log 'STORAGE_OUTCOME_REBOOT_RETURNED; NO_RETRY'
    return 1
}
