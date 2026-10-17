#!/bin/sh
# Add a small signed development layer to the existing RAM chroot.
set -eu
BB=/bin/busybox
root=/run/lynx/alpine-3.24.2
expected_boot=${1:-}
[ -n "$expected_boot" ]
[ "$(cat /proc/sys/kernel/random/boot_id)" = "$expected_boot" ]
[ "$(cat "$root/etc/alpine-release")" = 3.24.2 ]
[ "$($BB readlink /proc/self/ns/mnt)" = "$($BB readlink /proc/1/ns/mnt)" ]
$BB awk '$2 == "/run" && $3 == "tmpfs" {good=1} END {exit !good}' /proc/mounts
for field in temperature_error voltage_error current_error capacity_error; do
    $BB grep -Fx "$field=0" /run/lynx/battery-last > /dev/null
done
sample=$($BB sed -n 's/^sample_uptime_seconds=//p' /run/lynx/battery-last)
now=$($BB awk '{print $1}' /proc/uptime)
$BB awk -v a="$now" -v b="$sample" 'BEGIN {exit !(a >= b && a-b <= 15)}'
temperature=$($BB sed -n 's/^temperature_millidegrees_celsius=//p' /run/lynx/battery-last)
capacity=$($BB sed -n 's/^capacity_percent=//p' /run/lynx/battery-last)
[ "$temperature" -gt 0 ]; [ "$temperature" -lt 35000 ]; [ "$capacity" -ge 20 ]
[ "$(cat /sys/class/power_supply/11e01000.i2c:mt6375@34:chg/online)" = 0 ]
for pidfile in /run/lynx/thermal-watch.pid /run/lynx/battery-watch.pid /run/lynx/thermal-cooling-watch/pid; do
    kill -0 "$(cat "$pidfile")"
done
available=$($BB awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
[ "$available" -ge 1048576 ]
[ "$(date +%s)" -gt 1700000000 ]
limit=$($BB df -Pk /run | $BB awk 'END {print $2}')
case "$limit" in
    131072) $BB mount -t tmpfs -o remount,size=256m tmpfs /run ;;
    262144) : ;;
    *) echo 'Unexpected RAM filesystem limit; refusing to change it' >&2; exit 1 ;;
esac
[ "$($BB df -Pk /run | $BB awk 'END {print $2}')" = 262144 ]
[ "$($BB df -Pk /run | $BB awk 'END {print $4}')" -ge 102400 ]
protected=$($BB chroot "$root" /sbin/apk info -v)
set -- python3 git make
for installed in $protected; do
    spec=$(printf '%s\n' "$installed" | $BB sed -E 's/^(.*)-([0-9][^-]*-r[0-9]+)$/\1=\2/')
    case "$spec" in *=*) ;; *) echo 'Unrecognized package version' >&2; exit 1;; esac
    set -- "$@" "$spec"
done
echo LYNX_ALPINE_DEVELOPMENT_INSTALL_BEGIN
$BB timeout -s TERM 50 $BB chroot "$root" /sbin/apk --cache-dir /var/cache/apk --cache-packages add "$@"
for installed in $protected; do
    spec=$(printf '%s\n' "$installed" | $BB sed -E 's/^(.*)-([0-9][^-]*-r[0-9]+)$/\1=\2/')
    $BB chroot "$root" /sbin/apk info -e "$spec" > /dev/null
done
$BB chroot "$root" /usr/bin/python3 - <<'PY'
import hashlib, json, platform, sqlite3, ssl, threading
assert platform.machine() == 'aarch64'
db = sqlite3.connect(':memory:')
assert db.execute('select 6 * 7').fetchone()[0] == 42
result = []
thread = threading.Thread(target=lambda: result.append(hashlib.sha256(b'Lynx').hexdigest()))
thread.start(); thread.join()
assert len(result) == 1
print(json.dumps({'python': platform.python_version(), 'architecture': platform.machine(),
                  'kernel': platform.release(), 'openssl': ssl.OPENSSL_VERSION,
                  'sqlite': sqlite3.sqlite_version, 'thread_and_sqlite_passed': True}))
PY
$BB chroot "$root" /usr/bin/git --version
$BB chroot "$root" /usr/bin/make --version
[ "$(cat /proc/sys/kernel/random/boot_id)" = "$expected_boot" ]
echo LYNX_ALPINE_DEVELOPMENT_PASS
cat /run/lynx/battery-last
$BB df -k /run
