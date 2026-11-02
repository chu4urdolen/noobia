#!/bin/sh
# Lynx stock LM3642 module loader. Never unload these modules: the vendor
# driver leaves callbacks registered with the flashlight core on removal.
set -eu

modules=/usr/local/lib/lynx/flashlight
test "$(uname -r)" = 5.10.149-android12-9-o-g311738fbb5a8
test "$(cat /sys/bus/i2c/devices/6-0063/name)" = lm3642_22823
grep -q '^mtk_pbm ' /proc/modules
health=$(/usr/local/bin/lynx-status --assert-ready)
printf '%s' "$health" | /usr/bin/python3 -c '
import json,sys
h=json.load(sys.stdin)
assert not h["issues"]
assert h["battery"]["capacity_percent"] >= 25
assert h["battery"]["temperature_mC"] < 35000
assert h["thermal"]["max_mC"] < 45000
'

load() {
    name=$1
    expected=$2
    source="$modules/$name.ko"
    test -r "$source"
    test "$(sha256sum "$source" | cut -c1-64)" = "$expected"
    if ! grep -q "^$name " /proc/modules; then
        /bin/busybox timeout 15 /sbin/insmod "$source"
    fi
    grep -q "^$name " /proc/modules
}

load mtk_battery_oc_throttling 2285905a04532af8eaf2a04ad436eb14b4c8a7fc2bdbeaed3e5f647005b0cdf3
load flashlight 58dbf6edb80115078739a3b008ef73a2bad734f9c4812a1f34b8e28ae36bb915
load lm3642_22823 96dc429c39453dbd0ba469069655bfafc43e329cc3216d912bb080e87b7bef67

test -L /sys/bus/i2c/devices/6-0063/driver
test -c /dev/flashlight
/usr/local/bin/lynx-flashlight-pulse --off >/dev/null
printf '%s\n' flashlight-ready
