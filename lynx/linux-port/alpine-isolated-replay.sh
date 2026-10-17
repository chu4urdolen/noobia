#!/bin/sh
# Read verified inputs from inherited FD 3, entirely inside a new mount namespace.
set -eu
BB=/bin/busybox
expected_boot=${1:-}
parent_namespace=${2:-}
[ -n "$expected_boot" ]
[ -n "$parent_namespace" ]
[ "$(cat /proc/sys/kernel/random/boot_id)" = "$expected_boot" ]
child_namespace=$($BB readlink /proc/self/ns/mnt)
[ "$child_namespace" != "$parent_namespace" ]
[ "$($BB readlink /proc/1/ns/mnt)" = "$parent_namespace" ]
echo "isolated_mount_namespace=$child_namespace"
echo "original_mount_namespace=$parent_namespace"
# Caller uses unshare --propagation private. Verify that before detaching /run.
if $BB grep -Eq '(shared|master|propagate_from):[0-9]+' /proc/self/mountinfo; then
    echo 'Mount propagation is not private' >&2
    exit 1
fi
$BB umount -l /run
# Do not leave hidden inherited child mounts at the paths being recreated.
$BB awk '$5 == "/run" || index($5, "/run/") == 1 {bad=1} END {exit bad}' /proc/self/mountinfo
$BB mount -t tmpfs -o size=64m,mode=0755,nosuid tmpfs /run
inputs=/run/lynx/alpine-stage-isolated
$BB mkdir -p "$inputs"
$BB tar -xf - -C "$inputs" <&3
exec 3<&-
$BB sh "$inputs/stage.sh" --install "$expected_boot" "$inputs"
$BB sh "$inputs/stage.sh" --verify "$expected_boot" "$inputs"
root=/run/lynx/alpine-3.24.2
$BB test -r "$root/proc/meminfo"
$BB test -r "$root/sys/devices/system/cpu/online"
$BB chroot "$root" /bin/busybox free -m
$BB chroot "$root" /usr/bin/strace --version
echo LYNX_ALPINE_ISOLATED_COLD_REPLAY_PASS
# No service or background process is started. These mounts die with this shell.
