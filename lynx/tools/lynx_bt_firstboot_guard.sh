#!/bin/sh
# Started by lynx-bluetooth's OpenRC start_pre only for an explicit boot trial.
set -eu
marker=/etc/lynx/bt-firstboot-trial
state=/run/lynx/bt-firstboot-guard
test -f "$marker" || exit 0
mkdir -p "$state"
seconds=$(cat "$marker")
case "$seconds" in ''|*[!0-9]*) exit 2 ;; esac
test "$seconds" -ge 5 && test "$seconds" -le 900 || exit 2
printf '%s\n' "$$" > "$state/pid"
printf 'LYNX_BT_FIRSTBOOT_GUARD started boot_id=%s timeout=%ss\n' \
    "$(cat /proc/sys/kernel/random/boot_id)" "$seconds" \
    >> /var/log/lynx-bt-firstboot-guard.log
elapsed=0
while [ "$elapsed" -lt "$seconds" ]; do
    sleep 5
    test -f "$marker" || exit 0
    elapsed=$((elapsed + 5))
done
echo "LYNX_BT_FIRSTBOOT_GUARD timeout=${seconds}s; stopping radio" \
    >> /var/log/lynx-bt-firstboot-guard.log
rc-update del lynx-bluetooth default >> /var/log/lynx-bt-firstboot-guard.log 2>&1 || true
rc-service lynx-bluetooth stop >> /var/log/lynx-bt-firstboot-guard.log 2>&1 || true
rm -f "$marker"
