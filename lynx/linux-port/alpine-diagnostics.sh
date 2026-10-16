#!/bin/sh
# Package changes stay inside the verified RAM rootfs. No services are started.
set -eu
root=/run/lynx/alpine-3.24.2
test "$(cat "$root/etc/alpine-release")" = 3.24.2
test ! -e "$root/lynx-diagnostics-ready"
awk '$2=="/run" && ($3=="tmpfs" || $3=="ramfs") {ok=1} END {exit !ok}' /proc/mounts
test "$(date +%s)" -gt 1700000000
for f in /run/lynx/thermal-watch.pid /run/lynx/battery-watch.pid /run/lynx/thermal-cooling-watch/pid; do
    kill -0 "$(cat "$f")"
done
temperature=$(sed -n 's/^temperature_millidegrees_celsius=//p' /run/lynx/battery-last)
test "$temperature" -gt 0
test "$temperature" -lt 35000
if [ ! -e "$root/etc/resolv.conf" ]; then
    cp /etc/resolv.conf "$root/etc/resolv.conf"
fi
test -s "$root/etc/ssl/cert.pem"
for spec in 'null 1 3' 'zero 1 5' 'random 1 8' 'urandom 1 9'; do
    set -- $spec
    if [ ! -e "$root/dev/$1" ]; then
        mknod -m 666 "$root/dev/$1" c "$2" "$3"
    fi
    test -c "$root/dev/$1"
done
echo LYNX_ALPINE_APK_INSTALL_BEGIN
/bin/busybox chroot "$root" /usr/bin/timeout -s TERM 40 /sbin/apk --no-cache add strace
echo LYNX_ALPINE_APK_INSTALL_PASS
/bin/busybox chroot "$root" /usr/bin/strace --version
/bin/busybox chroot "$root" /usr/bin/strace -f -o /tmp/lynx-strace-smoke.log /bin/true
test -s "$root/tmp/lynx-strace-smoke.log"
head -n 12 "$root/tmp/lynx-strace-smoke.log"
echo LYNX_ALPINE_STRACE_PASS
date -u > "$root/lynx-diagnostics-ready"
echo BATTERY_AFTER
cat /run/lynx/battery-last
