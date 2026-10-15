# Return a coarse code using normal read-only kernel interfaces.
# Values describe the first missing condition, not a captured kernel error log.
lynx_binding_profile() {
    $BB grep -Eq '(^|[[:space:]])fw_devlink=permissive([[:space:]]|$)' /proc/cmdline || return 1
    [ -d /sys/bus/platform/drivers/ufshcd-mtk ] || return 2
    profile_ufs=''
    profile_reset_bound=0
    for profile_device in /sys/bus/platform/devices/*; do
        [ -L "$profile_device/of_node" ] || continue
        profile_node=$($BB readlink -f "$profile_device/of_node") || continue
        case "$profile_node" in
            */ufshci@112b0000) profile_ufs=$profile_device ;;
            */syscon@10001000/reset-controller)
                if [ -L "$profile_device/driver" ]; then
                    profile_driver=$($BB readlink "$profile_device/driver")
                    case "$profile_driver" in */ti-syscon-reset) profile_reset_bound=1 ;; esac
                fi
                ;;
        esac
    done
    [ -n "$profile_ufs" ] || return 3
    [ "$profile_reset_bound" = 1 ] || return 4
    profile_vemc=0
    for profile_name in /sys/class/regulator/*/name; do
        [ -f "$profile_name" ] || continue
        if $BB grep -iq vemc "$profile_name"; then profile_vemc=1; break; fi
    done
    [ "$profile_vemc" = 1 ] || return 5
    if [ -f "$profile_ufs/waiting_for_supplier" ]; then
        IFS= read -r profile_waiting < "$profile_ufs/waiting_for_supplier"
        [ "$profile_waiting" != 1 ] || return 6
    fi
    return 7
}
