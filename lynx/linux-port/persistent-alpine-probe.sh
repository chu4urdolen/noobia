#!/bin/sh
# Read-only live probe for Lynx's persistent Alpine root. Run via pinned SSH:
#   sh -s -- EXPECTED_BOOT_ID < persistent-alpine-probe.sh
# This does not replace PID 1, enable services, or write userdata.
set -eu
BB=/bin/busybox
BOOT_ID=${1:-}
case "$BOOT_ID" in
    ????????-????-????-????-????????????) ;;
    *) echo 'PERSISTENT_PROBE_REFUSED invalid boot ID' >&2; exit 2 ;;
esac
[ "$(cat /proc/sys/kernel/random/boot_id)" = "$BOOT_ID" ]
[ "$(cat /run/lynx/health-bootstrap/ready)" = ready ]
$BB sh /run/lynx/lynx-health-supervisor.sh --once >/dev/null
$BB grep -Fx 'PARTNAME=userdata' /sys/class/block/sdc85/uevent >/dev/null
[ "$(cat /sys/class/block/sdc85/size)" = 466026432 ]
[ -b /dev/sdc85 ]
! $BB grep -Eq '^/dev/sdc85 |^/dev/block/by-name/userdata ' /proc/mounts
identity=$($BB blkid /dev/sdc85)
case "$identity" in
    *'LABEL="LYNXROOT"'*'UUID="13dc3665-b062-405e-b674-ceae8972fc0f"'*'TYPE="ext4"'*) ;;
    *) echo 'PERSISTENT_PROBE_REFUSED ext4 identity differs' >&2; exit 3 ;;
esac
root=/run/lynx/persistent-alpine-probe
$BB mkdir -p "$root"
! $BB grep -F " $root " /proc/mounts >/dev/null
mounted_root=0
mounted_proc=0
mounted_sys=0
mounted_dev=0
mounted_run=0
cleanup() {
    [ "$mounted_run" = 0 ] || $BB umount "$root/run" || true
    [ "$mounted_dev" = 0 ] || $BB umount "$root/dev" || true
    [ "$mounted_sys" = 0 ] || $BB umount "$root/sys" || true
    [ "$mounted_proc" = 0 ] || $BB umount "$root/proc" || true
    [ "$mounted_root" = 0 ] || $BB umount "$root" || true
}
trap cleanup EXIT
$BB mount -t ext4 -o ro,noload /dev/sdc85 "$root"
mounted_root=1
[ "$(cat "$root/etc/alpine-release")" = 3.24.2 ]
[ -x "$root/sbin/openrc-init" ]
[ -x "$root/etc/init.d/lynx-health" ]
[ "$(readlink "$root/etc/runlevels/default/lynx-health")" = ../../init.d/lynx-health ]
for point in proc sys dev run; do [ -d "$root/$point" ]; done
$BB mount -o bind /proc "$root/proc"
mounted_proc=1
$BB mount -o bind /sys "$root/sys"
mounted_sys=1
$BB mount -o bind /dev "$root/dev"
mounted_dev=1
$BB mount -o bind /run "$root/run"
mounted_run=1
printf 'BOOT_ID=%s\n' "$BOOT_ID"
printf 'ROOT_ID=%s\n' "$identity"
printf 'PID1=%s\n' "$(readlink /proc/1/exe)"
printf 'ALPINE_RELEASE=%s\n' "$(cat "$root/etc/alpine-release")"
printf 'PYTHON='; $BB chroot "$root" /usr/bin/python3 --version
printf 'GIT='; $BB chroot "$root" /usr/bin/git --version
printf 'PROC='; $BB chroot "$root" /bin/cat /proc/sys/kernel/ostype
printf 'OPENRC='; [ -x "$root/sbin/openrc-init" ] && echo ready
printf 'HEALTH_SERVICE='; [ -x "$root/etc/init.d/lynx-health" ] && echo installed
printf 'PERSISTENT_ALPINE_PROBE_PASSED\n'
