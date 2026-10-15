# Observational kernel tracing. Only our new instance/group is changed.
# No return-value replacement, raw-address probe, partition write or global clear.
lynx_driver_trace_setup() {
    trace_root=/sys/kernel/tracing
    if [ ! -f "$trace_root/kprobe_events" ]; then
        $BB mount -t tracefs tracefs "$trace_root" || return 1
    fi
    [ -f "$trace_root/kprobe_events" ] || return 1
    trace_instance=$trace_root/instances/lynx_boot
    [ ! -e "$trace_instance" ] && [ ! -e "$trace_root/events/lynx_ufs" ] || return 1
    $BB mkdir "$trace_instance" || return 1
    printf '%s\n' 'r32:lynx_ufs/init_return ufshcd_pltfrm_init ret=$retval:s32' >> "$trace_root/kprobe_events" || return 1
    # device.kobj is the first member, and kobject.name is its first member.
    # The supplied OnePlus headers verify both offsets; fetches fault safely.
    printf '%s\n' 'p:lynx_ufs/domain_enter dev_pm_domain_attach name=+0(+0($arg1)):string' >> "$trace_root/kprobe_events" || return 1
    printf '%s\n' 'r32:lynx_ufs/domain_return dev_pm_domain_attach ret=$retval:s32' >> "$trace_root/kprobe_events" || return 1
    # Standard deferred module probes: enabled before the driver is loaded.
    printf '%s\n' 'p:lynx_ufs/mtk_probe_enter ufs_mediatek_mod:ufs_mtk_probe' >> "$trace_root/kprobe_events" || return 1
    printf '%s\n' 'r32:lynx_ufs/mtk_probe_return ufs_mediatek_mod:ufs_mtk_probe ret=$retval:s32' >> "$trace_root/kprobe_events" || return 1
    printf '%s\n' 'r32:lynx_ufs/health_pid __arm64_sys_getpid ret=$retval:s32' >> "$trace_root/kprobe_events" || return 1
    printf '%s\n' 'p:lynx_ufs/supplier_enter device_links_check_suppliers name=+0(+0($arg1)):string' >> "$trace_root/kprobe_events" || return 1
    printf '%s\n' 'r32:lynx_ufs/supplier_return device_links_check_suppliers ret=$retval:s32' >> "$trace_root/kprobe_events" || return 1
    printf '%s\n' 'p:lynx_ufs/pins_enter pinctrl_bind_pins name=+0(+0($arg1)):string' >> "$trace_root/kprobe_events" || return 1
    printf '%s\n' 'r32:lynx_ufs/pins_return pinctrl_bind_pins ret=$retval:s32' >> "$trace_root/kprobe_events" || return 1
    printf '%s\n' 'p:lynx_ufs/match_enter platform_match name=+0(+0($arg1)):string driver=+0($arg2):string' >> "$trace_root/kprobe_events" || return 1
    printf '%s\n' 'r32:lynx_ufs/match_return platform_match ret=$retval:s32' >> "$trace_root/kprobe_events" || return 1
    printf '%s\n' 'p:lynx_ufs/dma_enter platform_dma_configure name=+0(+0($arg1)):string' >> "$trace_root/kprobe_events" || return 1
    printf '%s\n' 'r32:lynx_ufs/dma_return platform_dma_configure ret=$retval:s32' >> "$trace_root/kprobe_events" || return 1
    printf '%s\n' 'p:lynx_ufs/platform_enter platform_drv_probe name=+0(+0($arg1)):string' >> "$trace_root/kprobe_events" || return 1
    printf '%s\n' 'r32:lynx_ufs/platform_return platform_drv_probe ret=$retval:s32' >> "$trace_root/kprobe_events" || return 1
    printf '4096\n' > "$trace_instance/buffer_size_kb" || return 1
    for trace_event in init_return domain_enter domain_return mtk_probe_enter mtk_probe_return health_pid supplier_enter supplier_return pins_enter pins_return match_enter match_return dma_enter dma_return platform_enter platform_return; do
        printf '1\n' > "$trace_instance/events/lynx_ufs/$trace_event/enable" || return 1
    done
    printf '1\n' > "$trace_instance/tracing_on" || return 1
    $BB sh -c 'echo $$' > /run/lynx/trace-health-pid || return 1
    return 0
}
lynx_driver_trace_capture() {
    # Stop recording without unregistering possibly active return probes.
    $BB sh -c 'echo $$' > /run/lynx/trace-health-pid || return 1
    printf '0\n' > "$trace_instance/tracing_on" || return 1
    $BB cat "$trace_instance/trace" > /run/lynx/driver-trace.log || return 1
    $BB chmod 600 /run/lynx/driver-trace.log || return 1
    $BB grep 'lynx_ufs/' "$trace_root/kprobe_profile" > /run/lynx/driver-trace-profile.log
    $BB chmod 600 /run/lynx/driver-trace-profile.log
    $BB dmesg > /run/lynx/kernel-dmesg.log
    $BB chmod 600 /run/lynx/kernel-dmesg.log
    if [ ! -f /sys/kernel/debug/devices_deferred ]; then
        $BB mount -t debugfs debugfs /sys/kernel/debug
    fi
    if [ -f /sys/kernel/debug/devices_deferred ]; then
        $BB cat /sys/kernel/debug/devices_deferred > /run/lynx/devices-deferred.log
        $BB chmod 600 /run/lynx/devices-deferred.log
    fi
    return 0
}
