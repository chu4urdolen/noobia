# Encode bootstrap result directly; does not depend on persistent logs.
lynx_bootstrap_timing_clock() {
    IFS=' ' read -r bt_uptime bt_unused < /proc/uptime || return 1
    bt_seconds=${bt_uptime%%.*}
    case "$bt_seconds" in ''|*[!0-9]*) return 1 ;; esac
}
lynx_bootstrap_timing_return() {
    IFS= read -r bt_start < /run/lynx/bootstrap-timing-start || return 1
    case "$bt_start" in ''|*[!0-9]*) return 1 ;; esac
    bt_code=6
    if [ -f /run/lynx/bootstrap-result ]; then
        IFS= read -r bt_result < /run/lynx/bootstrap-result || return 1
        case "$bt_result" in
            0) bt_code=0 ;; 151) bt_code=1 ;; 152) bt_code=2 ;;
            153) bt_code=3 ;; 154) bt_code=4 ;;
            ''|*[!0-9]*) bt_code=7 ;; *) bt_code=5 ;;
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
