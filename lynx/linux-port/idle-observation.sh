#!/bin/sh
# Read-only, paired observations. No idle-policy, suspend or device writes.
# Opening cpu_dma_latency briefly adds the kernel's default 2-second request;
# reading returns the aggregate constraint, then close removes that request.
set -u
snapshot() {
    echo "SNAPSHOT $1"
    cat /proc/uptime
    echo BATTERY
    cat /run/lynx/battery-last
    echo GLOBAL_CPU_LATENCY_US
    if [ -c /dev/cpu_dma_latency ]; then
        dd if=/dev/cpu_dma_latency bs=4 count=1 2>/dev/null | od -An -td4
    else
        echo unavailable
    fi
    echo CPU_IDLE
    for cpu in /sys/devices/system/cpu/cpu[0-9]*; do
        for state in "$cpu"/cpuidle/state*; do
            [ -d "$state" ] || continue
            printf '%s ' "$state"
            for field in name disable usage time rejected; do
                printf '%s=' "$field"
                if [ -r "$state/$field" ]; then
                    tr '\n' ' ' < "$state/$field"
                else
                    printf 'unavailable '
                fi
            done
            echo
        done
    done
    echo PROC_STAT
    cat /proc/stat
    echo INTERRUPTS
    cat /proc/interrupts
    echo SOFTIRQS
    cat /proc/softirqs
    echo WAKEUP_SOURCES
    cat /sys/kernel/debug/wakeup_sources
    echo WATCHERS
    tail -n 2 /run/lynx/thermal-watch.log /run/lynx/battery-watch.log
}
snapshot BEFORE
sleep 30
snapshot AFTER
