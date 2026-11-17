# Resolve the platform device by its live OF node, without guessing its bus name.
lynx_live_ufs_name() {
    live_ufs_name=''
    for live_device in /sys/bus/platform/devices/*; do
        [ -L "$live_device/of_node" ] || continue
        live_node=$($BB readlink -f "$live_device/of_node") || continue
        case "$live_node" in
            */ufshci@112b0000)
                [ -z "$live_ufs_name" ] || return 1
                live_ufs_name=${live_device##*/}
                ;;
        esac
    done
    [ -n "$live_ufs_name" ]
}
