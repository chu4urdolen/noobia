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

save_original() {
    "$BB" mkdir -p "$STATE"
    [ -s "$STATE/original_input_mA" ] && return 0
    v=$("$BB" cat "$CHG/input_current_limit" 2>/dev/null) || return 1
    case "$v" in ''|*[!0-9]*) return 1 ;; esac
    echo "$v" > "$STATE/original_input_mA"
}

apply_level() {
    lvl=$1
    if [ "$lvl" = 0 ]; then
        want=$("$BB" cat "$STATE/original_input_mA" 2>/dev/null) || return 1
    else
        want=$(limit_for "$lvl")
    fi
    orig=$("$BB" cat "$STATE/original_input_mA" 2>/dev/null || echo 0)
    # Never raise the limit above what the system had chosen itself.
    [ "$lvl" != 0 ] && [ "$want" -gt "$orig" ] && want=$orig
    echo "$want" > "$CHG/input_current_limit" 2>/dev/null || { log "WRITE_FAILED level=$lvl want=$want"; return 1; }
    got=$("$BB" cat "$CHG/input_current_limit" 2>/dev/null)
    echo "$lvl" > "$STATE/level"
    log "LEVEL level=$lvl input_limit_mA=$got (wanted $want)"
}

restore() {
    if [ -s "$STATE/original_input_mA" ]; then
        apply_level 0 && "$BB" rm -f "$STATE/original_input_mA" "$STATE/level"
    fi
}

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
    trap 'restore; exit 0' TERM INT
    lvl=0 up=0 down=0
    save_original || log "NO_CHARGER_CONTROL $CHG"
    while :; do
        if [ -e "$DISABLE" ]; then
            [ "$lvl" != 0 ] && { restore; lvl=0; }
            up=0 down=0
        elif t=$(battery_mC); then
            set -- $(decide "$lvl" "$t" "$up" "$down")
            if [ "$1" != "$lvl" ]; then
                save_original && apply_level "$1" && log "STEP from=$lvl to=$1 battery_mC=$t"
            fi
            lvl=$1 up=$2 down=$3
        else
            up=0 down=0   # an invalid reading never acts
        fi
        "$BB" sleep "$INTERVAL"
    done
}

case "${1:-}" in
    --once)
        t=$(battery_mC) || { echo "LYNX_CHARGE_GUARD_READ_FAILED"; exit 1; }
        echo "LYNX_CHARGE_GUARD_ONCE battery_mC=$t input_limit_mA=$("$BB" cat "$CHG/input_current_limit" 2>/dev/null) level=$("$BB" cat "$STATE/level" 2>/dev/null || echo 0)"
        ;;
    --watch) watch ;;
    --restore) restore; echo "LYNX_CHARGE_GUARD_RESTORED" ;;
    --decide) shift; decide "$@" ;;   # for tests
    *) echo 'Usage: lynx-charge-guard.sh --once|--watch|--restore' >&2; exit 2 ;;
esac
