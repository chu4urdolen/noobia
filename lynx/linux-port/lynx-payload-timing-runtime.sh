# Encode bootstrap result directly; does not depend on persistent logs.
lynx_bootstrap_timing_clock() {
    IFS=' ' read -r bt_uptime bt_unused < /proc/uptime || return 1
    bt_seconds=${bt_uptime%%.*}
    case "$bt_seconds" in ''|*[!0-9]*) return 1 ;; esac
}
lynx_bootstrap_timing_return() {
    IFS= read -r bt_start < /run/lynx/bootstrap-timing-start || return 1
    case "$bt_start" in ''|*[!0-9]*) return 1 ;; esac
    bt_code=8
    if [ -f /run/lynx/bootstrap-result ]; then
        IFS= read -r bt_result < /run/lynx/bootstrap-result || return 1
        case "$bt_result" in
            0) bt_code=0 ;;
            154)
                if IFS= read -r bt_payload < /run/lynx/payload-progress; then
                    case "$bt_payload" in 1|2|3|4|5|6|7) bt_code=$bt_payload ;; esac
                fi ;;
        esac
    fi
    # Existing bootstrap deadline is180s, so every slot is later than it.
    bt_target=$((240+5*bt_code))
    log "BOOTSTRAP_TIMING_RESULT code=$bt_code target=$bt_target"
    while :; do
        lynx_bootstrap_timing_clock || return 1
        [ "$bt_seconds" -ge "$((bt_start+bt_target))" ] && break
        $BB sleep 1
    done
    /bin/boot-proof-reboot
    log 'BOOTSTRAP_TIMING_RESET_RETURNED; NO_RETRY'
    return 1
}
