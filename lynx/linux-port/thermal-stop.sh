#!/bin/sh
# Independent, uncancelled RAM-only stop timer for the short sensor trial.
BB=/bin/busybox
$BB sleep 90
printf '<6>LYNX_THERMAL_STOP_REQUESTED\n' > /dev/kmsg
printf 'LYNX_THERMAL_STOP_REQUESTED\n'
exec "$BB" poweroff -f
