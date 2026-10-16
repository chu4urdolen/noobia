#!/bin/sh
# Session-only fallback after verified deep-idle rejection; no partition writes.
set -eu
base=/run/lynx/wfi-fallback
restore() {
    [ -s "$base/original-flags" ]
    while read -r path value; do
        case "$path" in /sys/devices/system/cpu/cpu[0-9]*/cpuidle/state[1-9]*/disable) ;; *) exit 1;; esac
        case "$value" in 0|1) ;; *) exit 1;; esac
        printf '%s\n' "$value" > "$path"
    done < "$base/original-flags"
    echo WFI_FALLBACK_ORIGINAL_FLAGS_RESTORED
}
status() {
    for cpu in /sys/devices/system/cpu/cpu[0-9]*; do
        for state in "$cpu"/cpuidle/state*; do
            [ -d "$state" ] || continue
            printf '%s name=%s disable=%s\n' "$state" "$(cat "$state/name")" "$(cat "$state/disable")"
        done
    done
}
case "${1:-}" in
    --apply)
        mkdir "$base"  # Refuse to overwrite saved originals or overlap.
        for cpu in /sys/devices/system/cpu/cpu[0-9]*; do
            [ "$(cat "$cpu/cpuidle/state0/name")" = WFI ]
            [ "$(cat "$cpu/cpuidle/state0/disable")" = 0 ]
            for state in "$cpu"/cpuidle/state*; do
                [ -d "$state" ] || continue
                case "$state" in */state0) continue;; esac
                value=$(cat "$state/disable")
                case "$value" in 0|1) ;; *) exit 1;; esac
                printf '%s %s\n' "$state/disable" "$value" >> "$base/original-flags"
            done
        done
        [ -s "$base/original-flags" ]
        trap restore EXIT
        trap 'exit 1' HUP INT TERM
        while read -r path value; do printf '1\n' > "$path"; done < "$base/original-flags"
        while read -r path value; do [ "$(cat "$path")" = 1 ]; done < "$base/original-flags"
        trap - EXIT HUP INT TERM
        echo WFI_FALLBACK_ACTIVE_UNTIL_RESTORE_OR_REBOOT
        status
        ;;
    --restore) restore; status;;
    --status) status;;
    *) echo 'Usage: wfi-fallback.sh --apply|--restore|--status' >&2; exit 2;;
esac
