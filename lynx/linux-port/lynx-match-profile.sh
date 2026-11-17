# Read-only live device matching profile. No binding, override or reprobe writes.
lynx_match_profile() {
    match_ufs=''
    for match_device in /sys/bus/platform/devices/*; do
        [ -L "$match_device/of_node" ] || continue
        match_node=$($BB readlink -f "$match_device/of_node") || continue
        case "$match_node" in */ufshci@112b0000) match_ufs=$match_device ;; esac
    done
    [ -n "$match_ufs" ] && [ -d /sys/bus/platform/drivers/ufshcd-mtk ] || return 1
    if [ -L "$match_ufs/driver" ]; then
        match_driver=$($BB readlink "$match_ufs/driver") || return 1
        case "$match_driver" in */ufshcd-mtk) return 2 ;; *) return 3 ;; esac
    fi
    [ -r "$match_ufs/driver_override" ] || return 1
    match_override=$($BB cat "$match_ufs/driver_override") || return 1
    case "$match_override" in ''|'(null)'|ufshcd-mtk) ;; *) return 3 ;; esac
    [ -r "$match_ufs/of_node/compatible" ] || return 1
    $BB tr '\000' '\n' < "$match_ufs/of_node/compatible" > /run/lynx/ufs-compatible.log || return 1
    $BB chmod 600 /run/lynx/ufs-compatible.log || return 1
    $BB grep -Fxq 'mediatek,mt8183-ufshci' /run/lynx/ufs-compatible.log || return 4
    [ -r /sys/bus/platform/drivers_autoprobe ] || return 1
    match_autoprobe=$($BB cat /sys/bus/platform/drivers_autoprobe) || return 1
    case "$match_autoprobe" in 0) return 5 ;; 1) ;; *) return 1 ;; esac
    if [ ! -f /sys/kernel/debug/devices_deferred ]; then
        $BB mount -t debugfs debugfs /sys/kernel/debug || return 1
    fi
    [ -r /sys/kernel/debug/devices_deferred ] || return 1
    $BB cat /sys/kernel/debug/devices_deferred > /run/lynx/devices-deferred.log || return 1
    $BB chmod 600 /run/lynx/devices-deferred.log || return 1
    match_name=${match_ufs##*/}
    if $BB awk -v name="$match_name" '$1==name { found=1 } END { exit !found }' /run/lynx/devices-deferred.log; then return 6; fi
    return 7
}
