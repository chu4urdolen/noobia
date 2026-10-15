# Normal stock driver registration, restricted to the audited targets.
lynx_radio_clock_find() {
    rc_bus=$1; rc_compat=$2; rc_expected_node=$3; rc_expected_driver=$4
    rc_match=''; rc_count=0
    for rc_dev in "$rc_bus"/*; do
        [ -f "$rc_dev/of_node/compatible" ] || continue
        rc_compatible=$($BB tr '\000' '\n' < "$rc_dev/of_node/compatible") || return 1
        printf '%s\n' "$rc_compatible" | $BB grep -Fxq "$rc_compat" || continue
        rc_node=$($BB readlink -f "$rc_dev/of_node") || return 1
        [ "$rc_node" = "$rc_expected_node" ] || return 1
        if [ "$rc_expected_driver" = none ]; then
            [ ! -e "$rc_dev/driver" ] && [ ! -L "$rc_dev/driver" ] || return 1
            if [ -f "$rc_dev/driver_override" ]; then
                rc_override=$($BB cat "$rc_dev/driver_override") || return 1
                case "$rc_override" in ''|'(null)') ;; *) return 1 ;; esac
            fi
        else
            rc_driver=$($BB readlink -f "$rc_dev/driver") || return 1
            [ "$rc_driver" = "$rc_expected_driver" ] || return 1
        fi
        rc_match=$rc_dev; rc_count=$((rc_count+1))
    done
    [ "$rc_count" = 1 ]
}
lynx_radio_clock_load() {
    [ ! -d /sys/module/mt6685_core ] && [ ! -d /sys/module/clkbuf ] || return 36
    rc_property_count=0
    while IFS=' ' read -r rc_node rc_property rc_expected rc_extra; do
        [ -z "$rc_extra" ] || return 36
        case "$rc_node" in /spmi@1c015000/mt6685_mfd|/spmi@1c015000/mt6685_mfd/mt6685_clock_buffer|/srclken-rc@1c00d000|/clock_buffer_ctrl) ;; *) return 36 ;; esac
        case "$rc_property" in ''|*[!a-zA-Z0-9_,.-]*) return 36 ;; esac
        rc_file=/sys/firmware/devicetree/base$rc_node/$rc_property
        [ -f "$rc_file" ] || return 36
        rc_actual=$($BB sha256sum "$rc_file") || return 36
        rc_actual=${rc_actual%% *}
        [ "$rc_actual" = "$rc_expected" ] || return 36
        rc_property_count=$((rc_property_count+1))
    done < /etc/lynx/radio-clock-properties || return 36
    [ "$rc_property_count" = 18 ] || return 36
    rc_hash=$($BB sha256sum /lib/modules/mt6685-core.ko) || return 36
    [ "${rc_hash%% *}" = 6784fabe8bd6b3c67d108f3e136abd049b06bdecbafdccf7da1e84137aacc8db ] || return 36
    rc_hash=$($BB sha256sum /lib/modules/clkbuf.ko) || return 36
    [ "${rc_hash%% *}" = 193be048dd1c87a2ddf324043657215dedd724cd43f1c80149e159cd03c97243 ] || return 36
    lynx_radio_clock_find /sys/bus/spmi/devices mediatek,mt6685 /sys/firmware/devicetree/base/spmi@1c015000/mt6685_mfd none || return 36
    lynx_radio_clock_find /sys/bus/platform/devices mediatek,srclken-rc /sys/firmware/devicetree/base/srclken-rc@1c00d000 none || return 36
    log 'RADIO_CLOCK_EXACT_TARGETS_VERIFIED'
    $BB insmod /lib/modules/mt6685-core.ko || return 37
    lynx_radio_clock_find /sys/bus/spmi/devices mediatek,mt6685 /sys/firmware/devicetree/base/spmi@1c015000/mt6685_mfd /sys/bus/spmi/drivers/mt6685 || return 37
    lynx_radio_clock_find /sys/bus/platform/devices mediatek,clock_buffer /sys/firmware/devicetree/base/spmi@1c015000/mt6685_mfd/mt6685_clock_buffer none || return 38
    for rc_dev in /sys/bus/platform/devices/*; do
        [ -f "$rc_dev/modalias" ] || continue
        rc_alias=$($BB cat "$rc_dev/modalias") || return 38
        [ "$rc_alias" = platform:mtk-srclken-rc ] || continue
        rc_node=$($BB readlink -f "$rc_dev/of_node") || return 38
        [ "$rc_node" = /sys/firmware/devicetree/base/srclken-rc@1c00d000 ] || return 38
    done
    $BB insmod /lib/modules/clkbuf.ko || return 38
    lynx_radio_clock_find /sys/bus/platform/devices mediatek,clock_buffer /sys/firmware/devicetree/base/spmi@1c015000/mt6685_mfd/mt6685_clock_buffer /sys/bus/platform/drivers/mtk-clock-buffer || return 38
    lynx_radio_clock_find /sys/bus/platform/devices mediatek,srclken-rc /sys/firmware/devicetree/base/srclken-rc@1c00d000 /sys/bus/platform/drivers/mtk-srclken-rc || return 39
    log 'RADIO_CLOCK_DRIVERS_BOUND; OUTPUTS_NOT_INDEPENDENTLY_MEASURED'
    return 0
}
