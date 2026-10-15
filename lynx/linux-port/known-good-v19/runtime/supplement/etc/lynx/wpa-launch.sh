# Foreground daemon owned by this shell: this build has no -f log option.
# Exit zero only after the real client receives PONG from the live daemon.
lynx_start_supplicant() {
    /sbin/wpa_supplicant -d -D "$2" -i "$1" -c "$3" > /run/lynx/wpa.log 2>&1 &
    lynx_wpa_pid=$!
    printf '%s\n' "$lynx_wpa_pid" > /run/lynx/wpa.pid
    lynx_wpa_try=0
    while [ "$lynx_wpa_try" -lt 10 ]; do
        if ! kill -0 "$lynx_wpa_pid" 2>/dev/null; then
            wait "$lynx_wpa_pid"
            printf '%s\n' "$?" > /run/lynx/wpa-exit-result
            return 1
        fi
        if [ -S "/run/wpa_supplicant/$1" ]; then
            if $BB timeout 1 /sbin/wpa_cli -p /run/wpa_supplicant -i "$1" ping > /run/lynx/wpa-ping 2>/run/lynx/wpa-ping.err; then
                if $BB grep -qx PONG /run/lynx/wpa-ping; then return 0; fi
            fi
        fi
        lynx_wpa_try=$((lynx_wpa_try+1))
        $BB sleep 1
    done
    kill "$lynx_wpa_pid" 2>/dev/null
    wait "$lynx_wpa_pid"
    printf '%s\n' "$?" > /run/lynx/wpa-exit-result
    return 1
}
