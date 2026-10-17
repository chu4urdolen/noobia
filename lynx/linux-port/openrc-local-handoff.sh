#!/bin/sh
# Offline Alpine PID 1 candidate. Called by BusyBox PID 1 only after the
# locally started health and Wi-Fi stages. On a pre-exec failure, the caller
# keeps the already monitored BusyBox rescue environment alive.
lynx_openrc_local_handoff() {
    LYNX_OPENRC_AUTHORITY=local
    . /etc/lynx/openrc-handoff-guard.sh || return 1
    lynx_openrc_handoff_guard || { log 'LOCAL_OPENRC_SAFETY_GUARD_REFUSED'; return 1; }

    alpine_archive=/usr/share/lynx/alpine-openrc-rootfs.cpio.gz
    alpine_expected=$($BB cat /usr/share/lynx/alpine-openrc-rootfs.sha256) || return 1
    case "$alpine_expected" in ''|*[!0-9a-f]*) return 1;; esac
    [ "${#alpine_expected}" -eq 64 ] || return 1
    alpine_actual=$($BB sha256sum "$alpine_archive") || return 1
    [ "${alpine_actual%% *}" = "$alpine_expected" ] || {
        log 'LOCAL_OPENRC_ROOTFS_HASH_MISMATCH'
        return 1
    }
    alpine_root=/run/alpine
    [ ! -e "$alpine_root/sbin/openrc-init" ] || return 1
    $BB mkdir -p "$alpine_root" || return 1
    (cd "$alpine_root" && $BB gzip -dc "$alpine_archive" | $BB cpio -idmu) || {
        log 'LOCAL_OPENRC_ROOTFS_EXTRACTION_FAILED'
        return 1
    }
    [ -x "$alpine_root/sbin/openrc-init" ] &&
        [ -x "$alpine_root/lib/ld-musl-aarch64.so.1" ] || return 1
    $BB mkdir -p "$alpine_root/proc" "$alpine_root/sys" "$alpine_root/dev" "$alpine_root/run" || return 1
    $BB mount -o bind /proc "$alpine_root/proc" || return 1
    $BB mount -o bind /sys "$alpine_root/sys" || return 1
    $BB mount -o bind /dev "$alpine_root/dev" || return 1
    $BB mount -o bind /run "$alpine_root/run" || return 1
    $BB sh /run/lynx/lynx-health-supervisor.sh --once || return 1
    log 'LOCAL_OPENRC_PID1_HANDOFF_BEGIN; BUSYBOX_WORKERS_RETAINED'
    exec $BB chroot "$alpine_root" /sbin/openrc-init
}
