#!/bin/sh
# lynx-power-mode: Lynx's two modes (Tom, 2026-11-23).
#
#   lynx-power-mode active            start everything that is "Lynx"
#   lynx-power-mode saving [REASON]   stop it all; the screen shows START
#   lynx-power-mode status            print "active" or "saving <reason>"
#
# Power saving is the boot default and where the guards send her when she is
# too warm or her battery is low. Nothing here ever shuts Lynx down or
# reboots her. Always-on services (Wi-Fi, SSH, display, logs, charging,
# watchers, heat recorder, NRP daemon) are never touched.
set -u
MODE_FILE=/var/lib/noobia/power-mode
LOCK=/run/lynx/power-mode.lock
# Started in order, stopped in reverse.
SERVICES="lynx-media lynx-bluetooth lynx-agent-worker noobia-autonomyd lynx-senses lynx-camera-sense"

say() { echo "LYNX_POWER_MODE $*"; /bin/busybox logger -t lynx-power-mode "$*" 2>/dev/null || true; }

current() { cat "$MODE_FILE" 2>/dev/null || echo "saving unknown"; }

set_mode() {
    mkdir -p "$(dirname "$MODE_FILE")"
    printf '%s\n' "$1" > "$MODE_FILE.tmp" && mv "$MODE_FILE.tmp" "$MODE_FILE"
}

take_lock() {
    mkdir -p /run/lynx
    if ! mkdir "$LOCK" 2>/dev/null; then
        old=$(cat "$LOCK/pid" 2>/dev/null)
        if [ -n "$old" ] && kill -0 "$old" 2>/dev/null; then
            say "busy: another mode switch is running (pid $old)"; exit 3
        fi
        rm -rf "$LOCK" && mkdir "$LOCK" || exit 3
    fi
    echo $$ > "$LOCK/pid"
    trap 'rm -rf "$LOCK"' EXIT
}

case "${1:-status}" in
    status)
        current ;;
    active)
        take_lock
        set_mode active
        say "ACTIVE: starting $SERVICES"
        for s in $SERVICES; do
            rc-service "$s" start >/dev/null 2>&1 || say "could not start $s"
        done
        say "ACTIVE: done" ;;
    saving)
        shift
        reason=$(printf '%s' "${*:-manual}" | tr -cd 'A-Za-z0-9 .,:()%-' | cut -c1-60)
        case "$(current)" in saving*) set_mode "saving $reason"; say "already saving ($reason)"; exit 0;; esac
        take_lock
        set_mode "saving $reason"
        say "SAVING ($reason): stopping services"
        for s in $(echo "$SERVICES" | tr ' ' '\n' | sed '1!G;h;$!d'); do
            rc-service "$s" stop >/dev/null 2>&1 || say "could not stop $s"
        done
        say "SAVING: done" ;;
    *)
        echo "usage: lynx-power-mode active|saving [reason]|status" >&2; exit 2 ;;
esac
