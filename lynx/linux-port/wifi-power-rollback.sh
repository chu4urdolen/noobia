#!/bin/busybox sh
# Revert only the Wi-Fi setting after the brief experiment, even if SSH drops.
# This never reboots or powers off the phone.
/bin/busybox sleep 30
/usr/sbin/iw dev wlan0 set power_save off
rc=$?
printf 'WIFI_PS_ROLLBACK_RETURN=%s\n' "$rc"
/usr/sbin/iw dev wlan0 get power_save
exit "$rc"
