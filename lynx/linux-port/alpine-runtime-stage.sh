#!/bin/sh
# Optional post-network RAM userspace stage. Never replaces PID 1 or services.
set -eu
mode=${1:-}
expected_boot=${2:-}
inputs=${3:-}
root=/run/lynx/alpine-3.24.2
BB=/bin/busybox
case "$mode" in --install|--verify) ;; *) echo 'Expected --install or --verify BOOT_ID INPUT_DIRECTORY' >&2; exit 2;; esac
[ -n "$expected_boot" ]
[ -d "$inputs" ]
[ ! -L "$inputs" ]
[ "$(cat /proc/sys/kernel/random/boot_id)" = "$expected_boot" ]
[ "$(uname -r)" = 5.10.149-android12-9-o-g311738fbb5a8 ]
outer_pid1=$($BB sha256sum /proc/1/exe)
outer_mounts=$(awk '$2 == "/proc" || $2 == "/sys" {print}' /proc/mounts)
awk '$2 == "/run" && $3 == "tmpfs" {good=1} END {exit !good}' /proc/mounts
inputs=$($BB readlink -f "$inputs")
case "$inputs" in /run/lynx/alpine-stage-*) ;; *) echo 'Inputs must be in the private RAM staging directory' >&2; exit 1;; esac
(cd "$inputs" && $BB sha256sum -c inputs.sha256)
if [ "$mode" = --install ]; then
    if [ -e "$root" ] || [ -L "$root" ]; then
        echo 'Refusing to overwrite an existing or partial rootfs' >&2
        exit 1
    fi
    available=$($BB df -Pk /run | $BB awk 'END {print $4}')
    [ "$available" -ge 32768 ]
    $BB mkdir "$root"
    $BB tar -xzf "$inputs/rootfs.tar.gz" -C "$root"
    $BB tar -xzf "$inputs/diagnostic-apks.tar.gz" -C "$root/tmp"
    for spec in 'null 1 3' 'zero 1 5' 'random 1 8' 'urandom 1 9'; do
        set -- $spec
        [ ! -e "$root/dev/$1" ]
        [ ! -L "$root/dev/$1" ]
        $BB mknod -m 666 "$root/dev/$1" c "$2" "$3"
    done
    if [ -f /etc/resolv.conf ]; then $BB cp /etc/resolv.conf "$root/etc/resolv.conf"; fi
    $BB timeout -s TERM 30 $BB chroot "$root" /bin/sh -c 'exec /sbin/apk --no-network --repositories-file /dev/null --cache-dir /tmp/lynx-offline-apks --cache-packages add /tmp/lynx-offline-apks/*.apk'
fi
[ -d "$root" ]
[ ! -L "$root" ]
[ "$(cat "$root/etc/alpine-release")" = 3.24.2 ]
(cd "$root" && $BB sha256sum -c "$inputs/essential.sha256")
while IFS= read -r spec; do
    [ -n "$spec" ]
    $BB chroot "$root" /sbin/apk info -e "$spec"
done < "$inputs/packages.spec"
if [ "$mode" = --install ]; then
    $BB sh "$inputs/observability.sh" --apply "$expected_boot"
else
    $BB sh "$inputs/observability.sh" --status "$expected_boot"
fi
$BB chroot "$root" /usr/bin/strace -f -o /tmp/lynx-runtime-stage.trace /bin/true
$BB grep -q 'exited with 0' "$root/tmp/lynx-runtime-stage.trace"
[ "$outer_pid1" = "$($BB sha256sum /proc/1/exe)" ]
[ "$outer_mounts" = "$(awk '$2 == "/proc" || $2 == "/sys" {print}' /proc/mounts)" ]
[ "$(cat /proc/sys/kernel/random/boot_id)" = "$expected_boot" ]
echo LYNX_ALPINE_RUNTIME_STAGE_READY
echo "mode=$mode"
echo "outer_pid1=$outer_pid1"
echo "boot_id=$expected_boot"
