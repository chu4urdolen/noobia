#!/bin/sh
# Host-armed, guarded BusyBox PID 1 -> persistent Alpine/OpenRC handoff.
# This is source-only until a separately validated boot_a candidate is built.
lynx_persistent_openrc_handoff() {
    LYNX_OPENRC_AUTHORITY=host /bin/busybox sh /etc/lynx/openrc-handoff-guard.sh --check || {
        log 'PERSISTENT_OPENRC_SAFETY_GUARD_REFUSED'
        return 1
    }
    $BB grep -Fx 'PARTNAME=userdata' /sys/class/block/sdc85/uevent >/dev/null || return 1
    [ "$(cat /sys/class/block/sdc85/size)" = 466026432 ] || return 1
    [ -b /dev/sdc85 ] || return 1
    ! $BB grep -Eq '^/dev/sdc85 |^/dev/block/by-name/userdata ' /proc/mounts || return 1
    persistent_identity=$($BB blkid /dev/sdc85) || return 1
    case "$persistent_identity" in
        *'LABEL="LYNXROOT"'*'UUID="13dc3665-b062-405e-b674-ceae8972fc0f"'*'TYPE="ext4"'*) ;;
        *) log 'PERSISTENT_OPENRC_ROOT_ID_REFUSED'; return 1 ;;
    esac
    persistent_root=/run/lynx/persistent-alpine
    [ ! -e "$persistent_root" ] || return 1
    $BB mkdir -m 700 "$persistent_root" || return 1
    $BB mount -t ext4 -o rw /dev/sdc85 "$persistent_root" || return 1
    persistent_valid=1
    [ "$(cat "$persistent_root/etc/alpine-release")" = 3.24.2 ] || persistent_valid=0
    [ -x "$persistent_root/sbin/openrc-init" ] || persistent_valid=0
    [ -x "$persistent_root/etc/init.d/lynx-health" ] || persistent_valid=0
    [ "$(readlink "$persistent_root/etc/runlevels/default/lynx-health")" = ../../init.d/lynx-health ] || persistent_valid=0
    for persistent_point in dev proc sys run; do
        [ -d "$persistent_root/$persistent_point" ] || persistent_valid=0
    done
    persistent_hash=$($BB sha256sum "$persistent_root/sbin/openrc-init") || persistent_valid=0
    [ "${persistent_hash%% *}" = 6180c8b047e41f2f5fdf581fa3e1a9835a6e2d0a4b3ceb3a60baf3f223217078 ] || persistent_valid=0
    persistent_hash=$($BB sha256sum "$persistent_root/lib/ld-musl-aarch64.so.1") || persistent_valid=0
    [ "${persistent_hash%% *}" = 32377e6d71725bb019e9ff6d5e9f16b4d5156d6f2c36504191c2d6a7c4d4a44d ] || persistent_valid=0
    persistent_hash=$($BB sha256sum "$persistent_root/etc/init.d/lynx-health") || persistent_valid=0
    [ "${persistent_hash%% *}" = 53e3efaf37c7f555c09f294bc5174b39183fac9df1db9489ae0ba93bdb50db53 ] || persistent_valid=0
    if [ "$persistent_valid" != 1 ]; then
        log 'PERSISTENT_OPENRC_ROOT_CONTENT_REFUSED'
        $BB umount "$persistent_root"
        return 1
    fi
    persistent_mounted=''
    for persistent_point in proc sys dev run; do
        if ! $BB mount -o bind "/$persistent_point" "$persistent_root/$persistent_point"; then
            log "PERSISTENT_OPENRC_BIND_FAILED point=$persistent_point"
            for persistent_undo in run dev sys proc; do
                case " $persistent_mounted " in *" $persistent_undo "*) $BB umount "$persistent_root/$persistent_undo" || true;; esac
            done
            $BB umount "$persistent_root" || true
            return 1
        fi
        persistent_mounted="$persistent_mounted $persistent_point"
    done
    if ! $BB chroot "$persistent_root" /usr/bin/python3 --version >/dev/null 2>&1; then
        log 'PERSISTENT_OPENRC_CHROOT_PROBE_FAILED'
        for persistent_undo in run dev sys proc; do
            $BB umount "$persistent_root/$persistent_undo" || true
        done
        $BB umount "$persistent_root" || true
        return 1
    fi
    $BB sh /run/lynx/lynx-health-supervisor.sh --once || {
        log 'PERSISTENT_OPENRC_FINAL_HEALTH_REFUSED'
        for persistent_undo in run dev sys proc; do
            $BB umount "$persistent_root/$persistent_undo" || true
        done
        $BB umount "$persistent_root" || true
        return 1
    }
    log 'PERSISTENT_OPENRC_PID1_HANDOFF_BEGIN; BUSYBOX_WORKERS_RETAINED'
    exec $BB chroot "$persistent_root" /sbin/openrc-init
}

lynx_persistent_openrc_wait_and_handoff() {
    persistent_token=$($BB cat /etc/lynx/session-token) || return 1
    IFS=' ' read -r persistent_uptime persistent_unused < /proc/uptime || return 1
    persistent_started=${persistent_uptime%%.*}
    case "$persistent_started" in ''|*[!0-9]*) return 1;; esac
    persistent_deadline=$((persistent_started+600))
    while :; do
        if [ -r /run/lynx/openrc-handoff-ready ]; then
            IFS= read -r persistent_armed < /run/lynx/openrc-handoff-ready || return 1
            if [ "$persistent_armed" = "$persistent_token" ]; then
                lynx_persistent_openrc_handoff
                return $?
            fi
        fi
        IFS=' ' read -r persistent_uptime persistent_unused < /proc/uptime || return 1
        persistent_now=${persistent_uptime%%.*}
        case "$persistent_now" in ''|*[!0-9]*) return 1;; esac
        [ "$persistent_now" -lt "$persistent_deadline" ] || {
            log 'PERSISTENT_OPENRC_ARM_TIMEOUT; BUSYBOX_RESCUE_ACTIVE'
            return 1
        }
        $BB sleep 1
    done
}
