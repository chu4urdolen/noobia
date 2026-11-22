#!/bin/sh
# Live swap of the boot image's RAM watchers for the glitch-proof versions
# (Gwyn for Tom, 2026-11-23). Never touches a hash-pinned boot file.
#
# Why: the boot image's health supervisor powers Lynx off after 3 failed
# health checks (~15 s). Its check flickers while the SoC crosses the cooling
# threshold (e.g. during a camera capture), so a warm moment can switch her
# off. The versions in /usr/libexec/lynx/quiet-watchers act only after 10
# consecutive bad readings, never power off, and stand down while
# /etc/lynx/power-thermal-guard.disable exists.
#
# Order matters: the supervisor is replaced FIRST (so nothing reacts to the
# other watchers restarting), each watcher is restarted with the exact pidfile
# lynx-health checks, and `rc-service lynx-health status` must pass at the end.
# The cooling watcher (soft throttle only, no poweroff) is left alone.
set -u
SRC=/usr/libexec/lynx/quiet-watchers
RUN=/run/lynx
BB=/bin/busybox

say() { echo "LYNX_WATCHERS_SWAP $*"; $BB logger -t lynx-watchers-swap "$*" 2>/dev/null || true; }

for f in lynx-health-supervisor.sh thermal-watch.sh battery-watch.sh; do
    [ -f "$SRC/$f" ] || { say "ABORT missing $SRC/$f"; exit 1; }
    if grep -q -E 'poweroff|openrc-shutdown|reboot' "$SRC/$f"; then
        say "ABORT $SRC/$f contains a shutdown command"; exit 1
    fi
done

running_copy_is_fixed() { grep -q READS_TO_ACT "$RUN/$1" 2>/dev/null || grep -q 'ge 10' "$RUN/$1" 2>/dev/null; }

# 1. Health supervisor (the only one that can power off on flicker).
if ! grep -q 'failures" -ge 10' "$RUN/lynx-health-supervisor.sh" 2>/dev/null; then
    for p in $(pgrep -f "sh $RUN/lynx-health-supervisor.sh --watch"); do kill "$p"; done
    sleep 1
    cp "$SRC/lynx-health-supervisor.sh" "$RUN/lynx-health-supervisor.sh" && chmod 700 "$RUN/lynx-health-supervisor.sh"
    rm -rf "$RUN/health-supervisor"
    start-stop-daemon -S -b -x $BB -- sh "$RUN/lynx-health-supervisor.sh" --watch
    sleep 2
    pid=$(cat "$RUN/health-supervisor/pid" 2>/dev/null)
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then say "supervisor swapped pid=$pid"
    else say "ERROR new supervisor not running"; exit 1; fi
else
    say "supervisor already glitch-proof"
fi

# 2. Temperature and battery watchers, with the pidfiles lynx-health reads.
swap() {
    name=$1 pidfile=$2
    if running_copy_is_fixed "$name"; then say "$name already glitch-proof"; return 0; fi
    for p in $(pgrep -f "sh $RUN/$name\$"); do kill "$p"; done
    sleep 1
    cp "$SRC/$name" "$RUN/$name" && chmod 700 "$RUN/$name"
    start-stop-daemon -S -b -m -p "$pidfile" -1 "$RUN/${name%.sh}.log" -2 "$RUN/${name%.sh}.log" \
        -x $BB -- sh "$RUN/$name"
    sleep 1
    pid=$(cat "$pidfile" 2>/dev/null)
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then say "$name swapped pid=$pid"
    else say "ERROR $name not running"; return 1; fi
}
swap thermal-watch.sh "$RUN/thermal-watch.pid" || exit 1
swap battery-watch.sh "$RUN/battery-watch.pid" || exit 1

# 3. The health chain must be satisfied.
sleep 6
if rc-service lynx-health status >/dev/null 2>&1; then say "OK lynx-health status passes"
else say "WARNING lynx-health status fails: $(/bin/sh $RUN/lynx-health-supervisor.sh --once 2>&1 | tail -1)"; exit 2; fi
