#!/bin/sh
# Load the two verified stock AW86907 modules without touching boot_a.
set -eu
root=/var/lib/lynx-haptic
firmware=/lib/firmware/aw8697_haptic_170.bin
led=/sys/class/leds/vibrator

test "$(uname -r)" = 5.10.149-android12-9-o-g311738fbb5a8
test -r "$firmware"
test "$(sha256sum "$firmware" | cut -c1-64)" = 9e8523531e61661d251d781457e5f4ba1f9894eaad0ddceb9217ed1c0fad4004

load_one() {
    name=$1
    digest=$2
    file="$root/$name.ko"
    test "$(sha256sum "$file" | cut -c1-64)" = "$digest"
    if ! grep -q "^$name " /proc/modules; then
        /bin/busybox timeout 12 /sbin/insmod "$file"
    fi
    grep -q "^$name " /proc/modules
}

load_one haptic_feedback 583a664f4cdbc6a57875cac165186c0fb9417b23c2c6c72f20e0a7b7bcedb07f
load_one haptic 2a6098b425efa146221703a9fa81d70f491540532721b9a3b352f709dd9e77a5

test -d "$led"
test -e "$led/oplus_duration"
test -e "$led/oplus_activate"
test "$(readlink /sys/bus/i2c/devices/12-005a/driver)" = ../../../../../bus/i2c/drivers/haptic_hv
printf 0 > "$led/oplus_activate"
