#!/bin/sh
# Called only after V19 Wi-Fi supervision returns. No valid gate means stay in
# the known BusyBox environment; only an authenticated, safety-checked gate can
# attempt the PID 1 handoff.
lynx_openrc_handoff() {
    wait_start=$($BB cut -d. -f1 /proc/uptime) || return 1
    case "$wait_start" in ''|*[!0-9]*) return 1;; esac
    # Leave room for the separate sensor and battery listeners to complete in
    # sequence while this PID 1 continues advertising the same boot token.
    wait_deadline=$((wait_start+1800))
    host=$(cat /etc/lynx/host-ip) || return 1
    token=$(cat /etc/lynx/session-token) || return 1
    while [ ! -f /run/lynx/openrc-handoff-ready ]; do
        wait_now=$($BB cut -d. -f1 /proc/uptime) || return 1
        case "$wait_now" in ''|*[!0-9]*) return 1;; esac
        [ "$wait_now" -lt "$wait_deadline" ] || { log 'OPENRC_GATE_TIMEOUT; BUSYBOX_RETAINED'; return 1; }
        # Keep the existing low-information discovery beacon alive so separate
        # host-side thermal and battery setup stages can run in sequence.
        printf 'LYNX_HELLO %s\n' "$token" | /usr/bin/nc -u -w 1 "$host" 5514 || true
        $BB sleep 1
    done
    . /etc/lynx/openrc-handoff-guard.sh || return 1
    lynx_openrc_handoff_guard || { log 'OPENRC_SAFETY_GUARD_REFUSED; BUSYBOX_RETAINED'; return 1; }

    archive=/usr/share/lynx/alpine-openrc-rootfs.cpio.gz
    expected=$(cat /usr/share/lynx/alpine-openrc-rootfs.sha256) || return 1
    case "$expected" in *[!0-9a-f]*|'') return 1;; esac
    [ "${#expected}" -eq 64 ] || return 1
    actual=$($BB sha256sum "$archive") || return 1
    actual=${actual%% *}
    [ "$actual" = "$expected" ] || { log 'OPENRC_ROOTFS_HASH_MISMATCH; BUSYBOX_RETAINED'; return 1; }

    root=/run/alpine
    [ ! -e "$root/sbin/openrc-init" ] || { log 'OPENRC_ROOT_ALREADY_EXISTS; BUSYBOX_RETAINED'; return 1; }
    $BB mkdir -p "$root" || return 1
    (cd "$root" && $BB gzip -dc "$archive" | $BB cpio -idmu) || { log 'OPENRC_ROOT_EXTRACTION_FAILED; BUSYBOX_RETAINED'; return 1; }
    [ -x "$root/sbin/openrc-init" ] && [ -x "$root/lib/ld-musl-aarch64.so.1" ] || { log 'OPENRC_EXECUTABLES_MISSING; BUSYBOX_RETAINED'; return 1; }
    $BB mkdir -p "$root/proc" "$root/sys" "$root/dev" "$root/run" || return 1
    $BB mount -o bind /proc "$root/proc" || return 1
    $BB mount -o bind /sys "$root/sys" || return 1
    $BB mount -o bind /dev "$root/dev" || return 1
    $BB mount -o bind /run "$root/run" || return 1
    log 'OPENRC_PID1_HANDOFF_BEGIN; BUSYBOX_WORKERS_RETAINED'
    exec $BB chroot "$root" /sbin/openrc-init
}
