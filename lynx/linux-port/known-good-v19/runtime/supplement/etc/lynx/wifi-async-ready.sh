# Wait only after the marked control timeout; never overlap a kernel request.
lynx_wifi_async_ready() {
    lynx_power_failure_code
    [ "$nt_station_code" = 25 ] || return 1
    wa_token=$($BB cat /etc/lynx/session-token) || return 1
    case "$wa_token" in ''|*[!0-9a-f]*) return 1 ;; esac
    [ "${#wa_token}" = 32 ] || return 1
    lynx_clock || return 1
    wa_start=$seconds
    wa_previous=''
    wa_stable=0
    while :; do
        lynx_clock || return 1
        [ "$seconds" -lt "$((wa_start+90))" ] || return 1
        wa_identity=''
        lynx_capture_wifi_worker_stack
        IFS= read -r wa_result < /run/lynx/wifi-worker-stack-result || return 1
        $BB dmesg | $BB tail -c 1048576 > /run/lynx/wifi-async-dmesg
        wa_success=$($BB awk -v marker="LYNX_STATION_ATTEMPT_BEGIN $wa_token" '
            $0 ~ ("(^|[[:space:]])" marker "$") { active=1; success=0; next }
            active && index($0,"wlanProbe: probe success, feature set:") { success=1 }
            active && index($0,"wlanProbe: probe failed, reason:") { success=0 }
            END { print (active && success) ? 1 : 0 }
        ' /run/lynx/wifi-async-dmesg) || return 1
        if [ "$wa_success" = 1 ] && [ "$wa_result" = 0 ] && $BB grep -Eq '(^|[^a-zA-Z0-9_])mtk_wland_thread_main\+0xe4/0x[0-9a-f]+([[:space:]]|$)' /run/lynx/wifi-worker-stack; then
            IFS= read -r wa_pid < /run/lynx/wifi-worker-pid || return 1
            case "$wa_pid" in ''|*[!0-9]*) return 1 ;; esac
            for wa_name in wlan0 wlan1; do
                wa_dev=/sys/class/net/$wa_name
                [ -d "$wa_dev/phy80211" ] || continue
                wa_module=$($BB readlink -f "$wa_dev/device/driver/module") || continue
                [ "$wa_module" = /sys/module/wlan_drv_gen4m_6983 ] || continue
                IFS= read -r wa_type < "$wa_dev/type" || continue
                [ "$wa_type" = 1 ] || continue
                IFS= read -r wa_ifindex < "$wa_dev/ifindex" || continue
                case "$wa_ifindex" in ''|*[!0-9]*) continue ;; esac
                [ "$wa_ifindex" -gt 0 ] || continue
                wa_identity=$wa_pid:$wa_name:$wa_ifindex
                break
            done
        fi
        if [ -n "$wa_identity" ] && [ "$wa_identity" = "$wa_previous" ]; then
            wa_stable=$((wa_stable+1))
        elif [ -n "$wa_identity" ]; then wa_stable=1
        else wa_stable=0; fi
        wa_previous=$wa_identity
        if [ "$wa_stable" -ge 2 ]; then
            lynx_clock || return 1
            [ "$seconds" -lt "$((wa_start+90))" ] || return 1
            printf '%s\n' "idle_samples=$wa_stable identity=$wa_identity elapsed=$((seconds-wa_start))" > /run/lynx/wifi-async-ready
            return 0
        fi
        $BB sleep 2
    done
}
