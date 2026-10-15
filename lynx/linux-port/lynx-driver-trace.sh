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
    printf '256\n' > "$trace_instance/buffer_size_kb" || return 1
    for trace_event in init_return domain_enter domain_return; do
        printf '1\n' > "$trace_instance/events/lynx_ufs/$trace_event/enable" || return 1
    done
    printf '1\n' > "$trace_instance/tracing_on" || return 1
    return 0
}
lynx_driver_trace_capture() {
    # Stop recording without unregistering possibly active return probes.
    printf '0\n' > "$trace_instance/tracing_on" || return 1
    $BB cat "$trace_instance/trace" > /run/lynx/driver-trace.log || return 1
    $BB chmod 600 /run/lynx/driver-trace.log || return 1
    $BB grep 'lynx_ufs/' "$trace_root/kprobe_profile" > /run/lynx/driver-trace-profile.log
    $BB chmod 600 /run/lynx/driver-trace-profile.log
    $BB dmesg > /run/lynx/kernel-dmesg.log
    $BB chmod 600 /run/lynx/kernel-dmesg.log
    return 0
}
