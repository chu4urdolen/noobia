# Supported MTU3 peripheral-role request; never access storage or raw registers.
# SYS_ROOT exists solely for the offline fixture test; native init leaves it unset.
lynx_usb_device_mode() {
    [ "${lynx_usb_role_done:-0}" = 0 ] || return 0
    lynx_sys=${SYS_ROOT:-/sys}
    [ -d "$lynx_sys/module/xhci_mtk_hcd" ] || return 0
    for lynx_controller in "$lynx_sys"/bus/platform/devices/11201000.*; do
        [ -d "$lynx_controller" ] || continue
        [ -L "$lynx_controller/driver" ] || continue
        lynx_driver=$($BB readlink -f "$lynx_controller/driver")
        [ "${lynx_driver##*/}" = mtu3 ] || continue
        [ -r "$lynx_controller/of_node/compatible" ] || continue
        $BB tr '\000' '\n' < "$lynx_controller/of_node/compatible" | $BB grep -qx 'mediatek,mtu3' || continue
        [ -r "$lynx_controller/of_node/dr_mode" ] || continue
        lynx_dr_mode=$($BB tr -d '\000' < "$lynx_controller/of_node/dr_mode")
        [ "$lynx_dr_mode" = otg ] || continue
        [ -e "$lynx_controller/of_node/usb-role-switch" ] || continue
        [ ! -e "$lynx_controller/of_node/enable-manual-drd" ] || continue
        # mode_store dereferences role_sw: require a registered switch for this parent.
        lynx_registered=0
        for lynx_role in "$lynx_sys"/class/usb_role/*; do
            [ -e "$lynx_role" ] || continue
            [ "$($BB readlink -f "$lynx_role/device")" = "$($BB readlink -f "$lynx_controller")" ] || continue
            lynx_registered=1
            break
        done
        [ "$lynx_registered" = 1 ] || continue
        [ -r "$lynx_controller/mode" ] && [ -w "$lynx_controller/mode" ] || continue
        lynx_old_mode=$($BB cat "$lynx_controller/mode")
        case "$lynx_old_mode" in 0|1|2|3) ;; *) continue ;; esac
        if [ "$lynx_old_mode" = 3 ] || printf '3\n' > "$lynx_controller/mode"; then
            lynx_usb_role_done=1
            log "Primary MTU3 peripheral mode requested (previous mode $lynx_old_mode)"
        else
            log 'Primary MTU3 peripheral-mode request failed'
        fi
        return 0
    done
    return 0
}
