# Narrow standard trace events. Each event name carries this boot's token.
# Use one bounded two-byte write for event activation and check readback.
lynx_ufs_persistent_trace_setup() {
    IFS=' ' read -r ufs_trace_token < /etc/lynx/session-token || return 1
    case "$ufs_trace_token" in ''|*[!0-9a-f]*) return 1 ;; esac
    [ "${#ufs_trace_token}" = 32 ] || return 1
    $BB mkdir -p /run/lynx/trace || return 1
    $BB mount -t tracefs tracefs /run/lynx/trace || return 1
    printf '%s\n' 1 > /run/lynx/trace-enable || return 1
    ufs_trace_index=0
    for ufs_trace_item in p:ufs_mediatek_mod:ufs_mtk_setup_ref_clk p:ufs_mediatek_mod:ufs_mtk_setup_ref_clk+0x88 p:ufs_mediatek_mod:ufs_mtk_setup_ref_clk+0x8c p:ufs_mediatek_mod:ufs_mtk_setup_ref_clk+0xa0 p:ufs_mediatek_mod:ufs_mtk_setup_ref_clk+0xa4 p:ufs_mediatek_mod:ufs_mtk_setup_ref_clk+0xf0 p:ufs_mediatek_mod:ufs_mtk_setup_ref_clk+0xf4 r32:ufs_mediatek_mod:ufs_mtk_setup_ref_clk p:ufs_mediatek_mod:ufs_mtk_boost_crypt; do
        ufs_trace_index=$((ufs_trace_index+1))
        ufs_trace_kind=${ufs_trace_item%%:*}
        ufs_trace_symbol=${ufs_trace_item#*:}
        ufs_trace_event="lx${ufs_trace_token}_${ufs_trace_index}"
        ufs_trace_args=''
        case "$ufs_trace_index" in
            1) ufs_trace_args=' on=$arg2:u8' ;;
            8) ufs_trace_args=' ret=$retval:s32' ;;
        esac
        printf '%s\n' "$ufs_trace_kind:lynx_ufs/$ufs_trace_event $ufs_trace_symbol$ufs_trace_args" >> /run/lynx/trace/kprobe_events || return 1
        $BB dd if=/run/lynx/trace-enable of="/run/lynx/trace/events/lynx_ufs/$ufs_trace_event/enable" bs=2 count=1 || return 1
        ufs_trace_enabled=$($BB cat "/run/lynx/trace/events/lynx_ufs/$ufs_trace_event/enable") || return 1
        [ "$ufs_trace_enabled" = 1 ] || return 1
    done
    log "UFS_PERSISTENT_TRACE_READY token=$ufs_trace_token events=$ufs_trace_index"
}
lynx_ufs_guarded_probe() {
    lynx_ufs_persistent_trace_setup || return 6
    lynx_diag_emit 515 16 || true
    [ "$($BB cat "$ufs_target/driver_override")" = lynx-block-ufs-probe ] || return 9
    [ ! -L "$ufs_target/driver" ] && [ ! -e "$ufs_target/driver" ] || return 9
    # Clearing the verified RAM override restores stock matching. No unbind.
    printf '\n' > "$ufs_target/driver_override" || return 9
    ufs_cleared=$($BB cat "$ufs_target/driver_override") || return 9
    case "$ufs_cleared" in ''|'(null)') ;; *) return 9 ;; esac
    [ -w /sys/bus/platform/drivers_probe ] || return 9
    ufs_probe_name=${ufs_target##*/}
    case "$ufs_probe_name" in ''|*[!a-zA-Z0-9_.-]*) return 9 ;; esac
    log "UFS_CONTROLLED_PROBE_BEGIN name=$ufs_probe_name"
    lynx_diag_emit 515 17 || true
    printf '%s\n' "$ufs_probe_name" > /run/lynx/ufs-probe-name || return 7
    $BB dd if=/run/lynx/ufs-probe-name of=/sys/bus/platform/drivers_probe bs=64 count=1 || return 7
    lynx_diag_emit 515 18 || true
    if [ -L "$ufs_target/driver" ]; then
        ufs_bound_driver=$($BB readlink -f "$ufs_target/driver") || return 8
        [ "$ufs_bound_driver" = /sys/bus/platform/drivers/ufshcd-mtk ] || return 8
        log 'UFS_CONTROLLED_PROBE_RETURNED_BOUND; BLOCK_ACCESS_NOT_TESTED'
        return 0
    fi
    return 8
}
