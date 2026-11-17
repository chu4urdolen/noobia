# Restore one omitted stock startup module, only for the exact audited DT target.
lynx_stock_clock_helper_guard() {
    [ ! -d /sys/module/clk_bringup ] || return 10
    clock_target=''
    clock_targets=0
    for clock_dev in /sys/bus/platform/devices/*; do
        [ -f "$clock_dev/of_node/compatible" ] || continue
        clock_compatible=$($BB tr '\000' '\n' < "$clock_dev/of_node/compatible") || return 10
        printf '%s\n' "$clock_compatible" | $BB grep -Eq '^(mediatek,clk-bring-up|mediatek,clk-post-ao)$' || continue
        [ "$clock_compatible" = mediatek,clk-bring-up ] || return 10
        clock_node=$($BB readlink -f "$clock_dev/of_node") || return 10
        [ "$clock_node" = /sys/firmware/devicetree/base/clkitg/bring-up ] || return 10
        [ ! -L "$clock_dev/driver" ] && [ ! -e "$clock_dev/driver" ] || return 10
        clock_hash=$($BB sha256sum "$clock_dev/of_node/clocks") || return 10
        clock_hash=${clock_hash%% *}
        [ "$clock_hash" = c6c820b927cb362d545b5798b35dec002e60f50805a78d4cc81ad7e90b698e9b ] || return 10
        clock_target=$clock_dev
        clock_targets=$((clock_targets+1))
    done
    [ "$clock_targets" = 1 ] || return 10
    clock_module_hash=$($BB sha256sum /lib/modules/clk-bringup.ko) || return 10
    clock_module_hash=${clock_module_hash%% *}
    [ "$clock_module_hash" = 4b62b692837be57cc9aab66136dec5d772840c8f572c37c20c59bda979216823 ] || return 10
    log 'STOCK_CLOCK_HELPER_EXACT_TARGET_VERIFIED'
}
lynx_stock_clock_helper_load() {
    lynx_stock_clock_helper_guard || return 10
    lynx_diag_emit 516 1 || true
    $BB insmod /lib/modules/clk-bringup.ko || return 11
    lynx_diag_emit 516 2 || true
    clock_driver=$($BB readlink -f "$clock_target/driver") || return 12
    [ "$clock_driver" = /sys/bus/platform/drivers/bring_up ] || return 12
    if [ ! -d /sys/kernel/debug/clk ]; then
        $BB mount -t debugfs debugfs /sys/kernel/debug || return 13
    fi
    # These are framework counters, not hardware register reads or controls.
    for clock_counter in clk_prepare_count clk_enable_count; do
        clock_count=$($BB cat "/sys/kernel/debug/clk/bus_aximem_sel/$clock_counter") || return 13
        case "$clock_count" in ''|*[!0-9]*) return 13 ;; esac
        [ "$clock_count" -gt 0 ] || return 13
    done
    lynx_diag_emit 516 3 || true
    log 'STOCK_CLOCK_HELPER_BOUND; BUS_AXIMEM_PREPARED_AND_ENABLED'
    return 0
}
