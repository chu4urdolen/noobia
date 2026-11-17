# Standard read-only procfs snapshot; all output remains in RAM.
lynx_capture_wifi_worker_stack() {
    ws_root=/proc
    ws_count=0
    ws_status=31
    for ws_dir in "$ws_root"/[0-9]*; do
        [ -d "$ws_dir" ] || continue
        ws_pid=${ws_dir##*/}
        case "$ws_pid" in ''|*[!0-9]*) continue ;; esac
        IFS= read -r ws_name < "$ws_dir/comm" || continue
        case "$ws_name" in mtk_wland_threa|mtk_wland_thread) ;; *) continue ;; esac
        ws_count=$((ws_count+1))
        [ "$ws_count" -le 1 ] || { ws_status=32; break; }
        printf '%s\n' "$ws_pid" > /run/lynx/wifi-worker-pid
        $BB head -c 4096 "$ws_dir/status" > /run/lynx/wifi-worker-status 2>/run/lynx/wifi-worker-status.err || true
        $BB head -c 4096 "$ws_dir/wchan" > /run/lynx/wifi-worker-wchan 2>/run/lynx/wifi-worker-wchan.err || true
        if $BB timeout 2 $BB head -c 16384 "$ws_dir/stack" > /run/lynx/wifi-worker-stack 2>/run/lynx/wifi-worker-stack.err; then
            if [ -s /run/lynx/wifi-worker-stack ]; then ws_status=0; else ws_status=33; fi
        else ws_status=33; fi
    done
    printf '%s\n' "$ws_status" > /run/lynx/wifi-worker-stack-result
}
