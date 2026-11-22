#!/bin/sh
# lynx-charge-guard: cool Lynx's battery by turning the CHARGER down, never
# by shutting her down (Principle 10; Gwyn for Tom, 2026-11-22).
#
# 2026-11-22 test: charging (+330 mA) warmed the battery ~2 C per 12 min
# while her own actions changed temperature by < 0.5 C. The MT6375 charger
# exposes writable limits, so the guard steps the charge current down as
# the battery warms and back up as it cools:
#
#   level 0  normal     original limits (read at start, restored on exit)
#   level 1  warm  >= WARM_mC     input limit LEVEL1_INPUT_mA
#   level 2  hot   >= HOT_mC      input limit LEVEL2_INPUT_mA
#   level 3  max   >= MAX_mC      input limit LEVEL3_INPUT_mA (lowest)
#
# A step DOWN needs READS_TO_ACT consecutive readings at or above the next
# threshold; a step UP needs READS_TO_ACT consecutive readings at least
# HYSTERESIS_mC below the current level's threshold. An unreadable or
# invalid reading never changes anything and resets both counters.
#
#   lynx-charge-guard.sh --once     print one reading and the decision, change nothing
#   lynx-charge-guard.sh --watch    run the guard
#   lynx-charge-guard.sh --restore  put the original limits back
#
# Disable: touch /etc/lynx/charge-guard.disable (the loop restores the
# original limits and idles while it exists).
set -u
BB=/bin/busybox
CHG=${CHARGE_GUARD_CHG:-"/sys/class/power_supply/11e01000.i2c:mt6375@34:chg"}
GAUGE=${CHARGE_GUARD_GAUGE:-/sys/bus/i2c/devices/7-0055/battery_snapshot}
STATE=${CHARGE_GUARD_STATE:-/var/lib/noobia/charge-guard}
DISABLE=${CHARGE_GUARD_DISABLE:-/etc/lynx/charge-guard.disable}
INTERVAL=${CHARGE_GUARD_INTERVAL:-10}
READS_TO_ACT=${CHARGE_GUARD_READS:-10}
WARM_mC=38000
HOT_mC=40000
MAX_mC=42000
HYSTERESIS_mC=2000
LEVEL1_INPUT_mA=300
LEVEL2_INPUT_mA=200
LEVEL3_INPUT_mA=100

log() { echo "LYNX_CHARGE_GUARD $*"; "$BB" logger -t lynx-charge-guard "$*" 2>/dev/null || true; }

battery_mC() {
    snap=$("$BB" cat "$GAUGE" 2>/dev/null) || return 1
    t=$(printf '%s\n' "$snap" | "$BB" sed -n 's/^temperature_millidegrees_celsius=//p')
    e=$(printf '%s\n' "$snap" | "$BB" sed -n 's/^temperature_error=//p')
    case "$t" in ''|*[!0-9]*) return 1 ;; esac
    [ "${e:-0}" = 0 ] || return 1
    [ "$t" -gt 0 ] && [ "$t" -lt 80000 ] || return 1
    echo "$t"
}

threshold() { case "$1" in 1) echo $WARM_mC ;; 2) echo $HOT_mC ;; 3) echo $MAX_mC ;; *) echo 0 ;; esac; }
limit_for() { case "$1" in 1) echo $LEVEL1_INPUT_mA ;; 2) echo $LEVEL2_INPUT_mA ;; 3) echo $LEVEL3_INPUT_mA ;; esac; }

boot_id() { "$BB" cat /proc/sys/kernel/random/boot_id 2>/dev/null || echo unknown; }

# The original limit is remembered together with the boot it was read in.
# The charger driver sets its own limit fresh at every boot, so a baseline
# from an earlier boot is stale and is discarded (Dushich review: a stale
# low baseline must never cap the charger forever).
save_original() {
    "$BB" mkdir -p "$STATE"
    if [ -s "$STATE/original_input_mA" ]; then
        [ "$("$BB" cat "$STATE/original_boot" 2>/dev/null)" = "$(boot_id)" ] && return 0
        log "STALE_BASELINE discarded from an earlier boot: $("$BB" cat "$STATE/original_input_mA")"
        "$BB" rm -f "$STATE/original_input_mA" "$STATE/original_boot" "$STATE/level"
    fi
    v=$("$BB" cat "$CHG/input_current_limit" 2>/dev/null) || return 1
    case "$v" in ''|*[!0-9]*) return 1 ;; esac
    echo "$v" > "$STATE/original_input_mA"
    boot_id > "$STATE/original_boot"
}

apply_level() {
    target=$1
    if [ "$target" = 0 ]; then
        want=$("$BB" cat "$STATE/original_input_mA" 2>/dev/null) || return 1
    else
        want=$(limit_for "$target")
    fi
    orig=$("$BB" cat "$STATE/original_input_mA" 2>/dev/null || echo 0)
    # Never raise the limit above what the system had chosen itself.
    [ "$target" != 0 ] && [ "$want" -gt "$orig" ] && want=$orig
    echo "$want" > "$CHG/input_current_limit" 2>/dev/null || { log "WRITE_FAILED level=$target want=$want"; return 1; }
    got=$("$BB" cat "$CHG/input_current_limit" 2>/dev/null)
    [ "$got" = "$want" ] || { log "READBACK_MISMATCH level=$target want=$want got=$got"; return 1; }
    echo "$target" > "$STATE/level"
    log "LEVEL level=$target input_limit_mA=$got"
}

restore() {
    [ -s "$STATE/original_input_mA" ] || return 0   # nothing of ours to undo
    apply_level 0 || return 1
    "$BB" rm -f "$STATE/original_input_mA" "$STATE/original_boot" "$STATE/level"
}

LOCK=$STATE/lock
take_lock() {
    "$BB" mkdir -p "$STATE"
    if ! "$BB" mkdir "$LOCK" 2>/dev/null; then
        old=$("$BB" cat "$LOCK/pid" 2>/dev/null)
        if [ -n "$old" ] && kill -0 "$old" 2>/dev/null; then
            log "ALREADY_RUNNING pid=$old"; return 1
        fi
        "$BB" rm -rf "$LOCK" && "$BB" mkdir "$LOCK" || return 1
    fi
    echo $$ > "$LOCK/pid"
}
drop_lock() { "$BB" rm -rf "$LOCK"; }

# Pure decision: level temp up_count down_count -> "level up_count down_count"
decide() {
    lvl=$1 t=$2 up=$3 down=$4
    next=$((lvl + 1))
    if [ "$lvl" -lt 3 ] && [ "$t" -ge "$(threshold $next)" ]; then
        up=$((up + 1)); down=0
        if [ "$up" -ge "$READS_TO_ACT" ]; then lvl=$next; up=0; fi
    elif [ "$lvl" -gt 0 ] && [ "$t" -lt $(( $(threshold $lvl) - HYSTERESIS_mC )) ]; then
        down=$((down + 1)); up=0
        if [ "$down" -ge "$READS_TO_ACT" ]; then lvl=$((lvl - 1)); down=0; fi
    else
        up=0; down=0
    fi
    echo "$lvl $up $down"
}

watch() {
    take_lock || exit 1
    trap 'restore; rc=$?; drop_lock; exit $rc' TERM INT
    lvl=0 up=0 down=0
    save_original || log "NO_CHARGER_CONTROL $CHG"
    while :; do
        if [ -e "$DISABLE" ]; then
            [ "$lvl" != 0 ] && { restore; lvl=0; }
            up=0 down=0
        elif t=$(battery_mC); then
            set -- $(decide "$lvl" "$t" "$up" "$down")
            new=$1 nup=$2 ndown=$3
            if [ "$new" != "$lvl" ]; then
                if save_original && apply_level "$new"; then
                    log "STEP from=$lvl to=$new battery_mC=$t"
                    lvl=$new
                fi
            fi
            up=$nup down=$ndown
        else
            up=0 down=0   # an invalid reading never acts
        fi
        # Sleep in the background so a TERM is handled at once, not after it.
        "$BB" sleep "$INTERVAL" & wait $!
    done
}

case "${1:-}" in
    --once)
        t=$(battery_mC) || { echo "LYNX_CHARGE_GUARD_READ_FAILED"; exit 1; }
        echo "LYNX_CHARGE_GUARD_ONCE battery_mC=$t input_limit_mA=$("$BB" cat "$CHG/input_current_limit" 2>/dev/null) level=$("$BB" cat "$STATE/level" 2>/dev/null || echo 0)"
        ;;
    --watch) watch ;;
    --restore)
        if restore; then echo "LYNX_CHARGE_GUARD_RESTORED"; else echo "LYNX_CHARGE_GUARD_RESTORE_FAILED"; exit 1; fi ;;
    --decide) shift; decide "$@" ;;   # for tests
    *) echo 'Usage: lynx-charge-guard.sh --once|--watch|--restore' >&2; exit 2 ;;
esac
