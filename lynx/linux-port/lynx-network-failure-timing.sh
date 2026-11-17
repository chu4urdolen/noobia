#!/bin/sh
# RAM-only result reporting, then the unchanged native reboot helper.
BB=/bin/busybox
lynx_network_timing_clock() {
    IFS=' ' read -r nt_uptime nt_unused < /proc/uptime || return 1
    nt_seconds=${nt_uptime%%.*}
    case "$nt_seconds" in ''|*[!0-9]*) return 1 ;; esac
}
lynx_network_timing_reboot() {
    IFS= read -r nt_start < /run/lynx/network-timing-start || return 1
    case "$nt_start" in ''|*[!0-9]*) return 1 ;; esac
    nt_code=24
    if [ -f /run/lynx/bootstrap-result ]; then
        IFS= read -r nt_boot < /run/lynx/bootstrap-result || return 1
        case "$nt_boot" in
            0)
                nt_code=18
                if [ -f /run/lynx/worker-result ]; then
                    IFS= read -r nt_worker < /run/lynx/worker-result || return 1
                    case "$nt_worker" in
                        0) nt_code=0 ;;
                        131|132|133|134|135|136|137|138|139|140|141|142|143|144|145|146)
                            nt_code=$((nt_worker-130)) ;;
                        *) nt_code=17 ;;
                    esac
                fi ;;
            151|152|153|154) nt_code=$((nt_boot-131)) ;;
            *) nt_code=19 ;;
        esac
    fi
    # Maximum180s bootstrap +240s Wi-Fi supervision precedes every slot.
    nt_target=$((480+5*nt_code))
    printf '<6>LYNX_NETWORK_TIMING code=%s target=%s\n' "$nt_code" "$nt_target" > /dev/kmsg || true
    while :; do
        lynx_network_timing_clock || return 1
        [ "$nt_seconds" -ge "$((nt_start+nt_target))" ] && break
        $BB sleep 1
    done
    /bin/boot-proof-reboot-native
    return 1
}
lynx_network_timing_reboot
