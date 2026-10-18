"""Build V25f: Wi-Fi/SSH before health with a bounded early power-off guard.

The proven V19 network startup took about 92 seconds; this image permits at
most 180 seconds without the automatic health watchers. The health stage has
its own independent 180-second timer. No phone contact or flashing here.
"""
from pathlib import Path

import build_selfboot_health_candidate as base

OUT = Path(__file__).resolve().parent.parent / 'linux-port/artifacts/selfboot-wifi-first-v25f-offline'

TAIL = b'''log 'LOCAL_BOOTSTRAP_READY; PREPARING_WIFI_FIRST_DIAGNOSTIC'
local_token=$($BB cat /etc/lynx/session-token) || stop
[ -n "$local_token" ] || stop
printf '%s\n' "$local_token" > /run/lynx/local-boot-ready.tmp || stop
$BB mv /run/lynx/local-boot-ready.tmp /run/lynx/local-boot-ready || stop
( $BB sleep 180; log 'EARLY_HEALTH_DEADLINE_POWER_OFF'; $BB poweroff -f ) > /run/lynx/early-health-timer.log 2>&1 < /dev/null &
early_health_timer=$!
printf '%s\n' "$early_health_timer" > /run/lynx/early-health-timer.pid
. /etc/lynx/wifi-runtime.sh || { log 'LOCAL_WIFI_SCRIPT_LOAD_FAILED'; $BB poweroff -f; /bin/boot-proof-reboot; stop; }
. /etc/lynx/wifi-local-supervise.sh || { log 'LOCAL_WIFI_SUPERVISOR_LOAD_FAILED'; $BB poweroff -f; /bin/boot-proof-reboot; stop; }
lynx_wifi_supervise_local || { $BB poweroff -f; stop; }
log 'LOCAL_WIFI_READY; PREPARING_GUARDED_HEALTH'
. /etc/lynx/autonomous-health-local-handoff.sh || { log 'LOCAL_HEALTH_SCRIPT_LOAD_FAILED'; $BB poweroff -f; /bin/boot-proof-reboot; stop; }
lynx_autonomous_health_local_handoff || { log 'LOCAL_HEALTH_BOOT_FAILED; POWER_OFF_REQUESTED'; $BB poweroff -f; /bin/boot-proof-reboot; stop; }
kill "$early_health_timer" || { log 'EARLY_HEALTH_TIMER_CANCEL_FAILED'; $BB poweroff -f; stop; }
wait "$early_health_timer" 2>/dev/null || true
log 'LOCAL_SELFBOOT_WIFI_SSH_HEALTH_ACTIVE; BUSYBOX_PID1_RESCUE_READY'
stop
'''


if __name__ == '__main__':
    base.main(out=OUT, new_tail=TAIL, variant='V25f-wifi-first-guarded')
