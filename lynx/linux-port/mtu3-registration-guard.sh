# RAM-only matching override. Never unbind an existing driver.
lynx_mtu3_registration_guard() {
    targets=''
    count=0
    for dev in /sys/bus/platform/devices/*; do
        [ -f "$dev/of_node/compatible" ] || continue
        compatible=$($BB tr '\000' '\n' < "$dev/of_node/compatible") || return 74
        printf '%s\n' "$compatible" | $BB grep -Fxq 'mediatek,mtu3' || continue
        node=$($BB readlink -f "$dev/of_node") || return 74
        case "$node" in
            /sys/firmware/devicetree/base/soc/usb0@11201000|/sys/firmware/devicetree/base/soc/usb1@11211000) ;;
            *) log 'MTU3_OVERRIDE_UNEXPECTED_NODE'; return 74 ;;
        esac
        [ ! -L "$dev/driver" ] && [ ! -e "$dev/driver" ] || return 74
        [ -f "$dev/driver_override" ] && [ -w "$dev/driver_override" ] || return 74
        old=$($BB cat "$dev/driver_override") || return 74
        case "$old" in ''|'(null)') ;; *) return 74 ;; esac
        targets="$targets $dev"
        count=$((count+1))
    done
    [ "$count" -ge 1 ] && [ "$count" -le 2 ] || return 74
    for dev in $targets; do
        printf '%s\n' 'lynx-block-mtu3-probe' > "$dev/driver_override" || return 74
        value=$($BB cat "$dev/driver_override") || return 74
        [ "$value" = lynx-block-mtu3-probe ] || return 74
    done
    log "MTU3_REGISTRATION_ONLY_GUARD_VERIFIED targets=$count"
}
lynx_mtu3_registration_load() {
    lynx_mtu3_registration_guard || return 74
    $BB insmod /lib/modules/mtu3.ko
}
