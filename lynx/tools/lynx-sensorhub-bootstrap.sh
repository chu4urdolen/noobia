#!/bin/sh
# Load the exact August Nord 3 sensor bridge after SCP and audio are ready.
set -eu
root=/var/lib/lynx-sensors/v1
snapshot=/sys/bus/i2c/devices/7-0055/battery_snapshot

test "$(uname -r)" = 5.10.149-android12-9-o-g311738fbb5a8
test -r "$snapshot"
test "$(sed -n 's/^gauge_device_type=//p' "$snapshot")" = 42495
test "$(sed -n 's/^capacity_error=//p' "$snapshot")" = 0
test "$(sed -n 's/^temperature_error=//p' "$snapshot")" = 0
capacity=$(sed -n 's/^capacity_percent=//p' "$snapshot")
temperature=$(sed -n 's/^temperature_millidegrees_celsius=//p' "$snapshot")
current=$(sed -n 's/^gauge_current_ma_signed=//p' "$snapshot")
test "$capacity" -ge 25
test "$temperature" -lt 35000
if test "$capacity" -lt 50; then test "$current" -gt 0; fi
test "$(cat /sys/class/thermal/thermal_zone0/temp)" -lt 45000
grep -q '^scp ' /proc/modules
grep -q '^mtk_tinysys_ipi ' /proc/modules
test -L /sys/bus/platform/devices/1c400000.scp/driver

load_one() {
    name=$1
    digest=$2
    file=$root/$name.ko
    test "$(sha256sum "$file" | cut -c1-64)" = "$digest"
    if ! grep -q "^$name " /proc/modules; then
        /bin/busybox timeout 20 /sbin/insmod "$file"
    fi
    grep -q "^$name " /proc/modules
}

load_one hf_manager 6556d801250d2f7c21d55542337df7b7f4793ecce48551603525b52d0617e677
load_one sensorhub 10eede8b4673d3cc81894ed76fa7a044eec10e90b52464483848bda10d93154e
attempt=0
until test -c /dev/hf_manager && grep -q 'bmi2xy acc' /proc/hf_manager; do
    attempt=$((attempt + 1))
    test "$attempt" -le 15
    sleep 1
done
printf 'LYNX_SENSORHUB_READY accelerometer=bmi2xy\n'
