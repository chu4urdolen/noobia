"""Build V25e: known V19 Wi-Fi/SSH first, local guarded health second.

The first V25d hardware attempt provided no SSH, so this candidate opens the
pinned diagnostic channel before trying the new automatic health path. It is
still an offline prototype; this build never contacts or flashes Lynx.
"""
from pathlib import Path

import build_selfboot_health_candidate as base

OUT = Path(__file__).resolve().parent.parent / 'linux-port/artifacts/selfboot-wifi-first-v25e-offline'

TAIL = b'''log 'LOCAL_BOOTSTRAP_READY; PREPARING_WIFI_FIRST_DIAGNOSTIC'
local_token=$($BB cat /etc/lynx/session-token) || stop
[ -n "$local_token" ] || stop
printf '%s\n' "$local_token" > /run/lynx/local-boot-ready.tmp || stop
$BB mv /run/lynx/local-boot-ready.tmp /run/lynx/local-boot-ready || stop
. /etc/lynx/wifi-runtime.sh || { log 'LOCAL_WIFI_SCRIPT_LOAD_FAILED'; /bin/boot-proof-reboot; stop; }
. /etc/lynx/wifi-local-supervise.sh || { log 'LOCAL_WIFI_SUPERVISOR_LOAD_FAILED'; /bin/boot-proof-reboot; stop; }
lynx_wifi_supervise_local || stop
log 'LOCAL_WIFI_READY; PREPARING_GUARDED_HEALTH'
. /etc/lynx/autonomous-health-local-handoff.sh || { log 'LOCAL_HEALTH_SCRIPT_LOAD_FAILED'; $BB poweroff -f; /bin/boot-proof-reboot; stop; }
lynx_autonomous_health_local_handoff || { log 'LOCAL_HEALTH_BOOT_FAILED; POWER_OFF_REQUESTED'; $BB poweroff -f; /bin/boot-proof-reboot; stop; }
log 'LOCAL_SELFBOOT_WIFI_SSH_HEALTH_ACTIVE; BUSYBOX_PID1_RESCUE_READY'
stop
'''


if __name__ == '__main__':
    base.main(out=OUT, new_tail=TAIL, variant='V25e-wifi-first')
