#!/bin/sh
# Recreate the verified MT6983 sound card after Alpine boots.
set -eu
root=/var/lib/lynx-audio/v1
manifest=$root/modules.sha256
firmware=/lib/firmware/tfa98xx.cnt

test "$(uname -r)" = 5.10.149-android12-9-o-g311738fbb5a8
test "$(sha256sum "$firmware" | cut -c1-64)" = d5d0f96d14b6fb0f324b162de3c3898f2caaac6ee6a5fad64cf9bc29f4e74e87
test -r "$manifest"

snapshot=/sys/bus/i2c/devices/7-0055/battery_snapshot
test -r "$snapshot"
field() { sed -n "s/^$1=//p" "$snapshot" | head -n 1; }
test "$(field gauge_device_type)" = 42495
test "$(field capacity_error)" = 0
test "$(field temperature_error)" = 0
test "$(field current_error)" = 0
capacity=$(field capacity_percent)
temperature=$(field temperature_millidegrees_celsius)
current=$(field gauge_current_ma_signed)
test "$capacity" -ge 25
test "$temperature" -lt 35000
if test "$capacity" -lt 50; then test "$current" -gt 0; fi
soc_temp=$(cat /sys/class/thermal/thermal_zone0/temp)
test "$soc_temp" -lt 45000

while read -r name digest file; do
    case "$name" in ''|*[!a-zA-Z0-9_]*) exit 1 ;; esac
    case "$digest" in *[!a-f0-9]*) exit 1 ;; esac
    path=$root/modules/$file
    test "$(sha256sum "$path" | cut -c1-64)" = "$digest"
    if ! grep -q "^$name " /proc/modules; then
        printf 'LYNX_AUDIO_LOAD %s\n' "$name"
        /bin/busybox timeout 20 /sbin/insmod "$path"
        grep -q "^$name " /proc/modules
    fi
done < "$manifest"

printf 'LYNX_AUDIO_MODULES_DONE\n'
# ALSA card registration can finish just after the final module's insmod exits.
attempt=0
until grep -q mt6983mt6338 /proc/asound/cards; do
    attempt=$((attempt + 1))
    test "$attempt" -le 15
    sleep 1
done
printf 'LYNX_AUDIO_CARD_READY\n'
amixer -c0 cset name=Speaker_L_Mute_Switch On >/dev/null
amixer -c0 cset name=Speaker_R_Mute_Switch On >/dev/null
printf %s tfa98xx.cnt > /sys/module/snd_soc_tfa98xx/parameters/fw_name
if ! amixer -c0 cget name='TFA98XX Firmware' | grep -q ': values=1'; then
    /bin/busybox timeout 15 amixer -c0 cset name='TFA98XX Firmware' 1 >/dev/null
fi
attempt=0
until amixer -c0 cget name='TFA98XX Firmware' | grep -q ': values=1'; do
    attempt=$((attempt + 1))
    test "$attempt" -le 15
    sleep 1
done
printf 'LYNX_AUDIO_FIRMWARE_READY\n'
amixer -c0 cget name=Speaker_L_Mute_Switch | grep -q ': values=1'
amixer -c0 cget name=Speaker_R_Mute_Switch | grep -q ': values=1'
printf 'LYNX_AUDIO_READY card=mt6983mt6338 battery=%s%%\n' "$capacity"
