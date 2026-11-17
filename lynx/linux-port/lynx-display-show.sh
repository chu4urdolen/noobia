#!/bin/sh
# Manual, bounded V49 visual proof. Tell the observer before using it.
# Reuses the exact atomic binary and brightness sequence seen on 2026-10-25.
set -eu

program=/usr/local/lib/lynx-display/lynx_drm_atomic_candidate
brightness=/sys/kernel/oplus_display/oplus_brightness
expected=0406aa15f90547d571271efdba5cd7566277dfb5e4e56f209c5c1f7e9d9271e5
mode=${1:---check}

test -c /dev/dri/card0
[ "$(cat /sys/class/drm/card0-DSI-1/status)" = connected ]
[ "$(cat "$brightness")" = 0 ]
got=$(sha256sum "$program")
got=${got%% *}
[ "$got" = "$expected" ] || { echo 'atomic program hash mismatch' >&2; exit 1; }

if [ "$mode" = --check ]; then
    /bin/busybox timeout 12 "$program" --atomic-test
    echo 'display is ready; no pixels shown'
    exit 0
fi

case "$mode" in
    *[!0-9]*|'') echo 'seconds must be 1..15' >&2; exit 2 ;;
esac
[ "$mode" -ge 1 ] && [ "$mode" -le 15 ] || {
    echo 'seconds must be 1..15' >&2; exit 2;
}

work=$(mktemp -d /run/lynx/display.XXXXXX)
pid=
cleanup() {
    printf '%s' 0 > "$brightness" || :
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null || :
        wait "$pid" 2>/dev/null || :
    fi
    rm -rf "$work"
}
trap cleanup EXIT HUP INT TERM

/bin/busybox timeout "$((mode + 10))" "$program" --show-atomic "$mode" > "$work/show.log" 2>&1 &
pid=$!
ready=0
n=0
while [ "$n" -lt 40 ]; do
    if grep -q 'displaying color bars' "$work/show.log"; then
        ready=1
        break
    fi
    kill -0 "$pid" 2>/dev/null || break
    /bin/busybox sleep 0.1
    n=$((n + 1))
done
if [ "$ready" -ne 1 ]; then
    cat "$work/show.log" >&2
    wait "$pid"
    exit 1
fi

printf '%s' 400 > "$brightness"
echo 'Lynx display on at brightness 400'
wait "$pid"
cat "$work/show.log"
echo 'Lynx display trial complete; restoring brightness zero'
