# RAM-only matching override. Validate exactly one stock UFS target first.
# Do not unbind, overwrite an existing override, or touch controller registers.
lynx_ufs_registration_guard() {
    ufs_target=''
    ufs_count=0
    for ufs_dev in /sys/bus/platform/devices/*; do
        [ -f "$ufs_dev/of_node/compatible" ] || continue
        ufs_compatible=$($BB tr '\000' '\n' < "$ufs_dev/of_node/compatible") || return 74
        printf '%s\n' "$ufs_compatible" | $BB grep -Fxq 'mediatek,mt8183-ufshci' || continue
        ufs_node=$($BB readlink -f "$ufs_dev/of_node") || return 74
        [ "$ufs_node" = /sys/firmware/devicetree/base/ufshci@112b0000 ] || return 74
        [ ! -L "$ufs_dev/driver" ] && [ ! -e "$ufs_dev/driver" ] || return 74
        [ -f "$ufs_dev/driver_override" ] && [ -w "$ufs_dev/driver_override" ] || return 74
        ufs_old=$($BB cat "$ufs_dev/driver_override") || return 74
        case "$ufs_old" in ''|'(null)') ;; *) return 74 ;; esac
        ufs_target=$ufs_dev
        ufs_count=$((ufs_count+1))
    done
    [ "$ufs_count" = 1 ] || return 74
    printf '%s\n' 'lynx-block-ufs-probe' > "$ufs_target/driver_override" || return 74
    ufs_value=$($BB cat "$ufs_target/driver_override") || return 74
    [ "$ufs_value" = lynx-block-ufs-probe ] || return 74
    log 'UFS_REGISTRATION_ONLY_GUARD_VERIFIED'
}
