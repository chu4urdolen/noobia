#!/bin/sh
# RAM-only bounded trial: disable failed deep states, preserve working WFI.
# A detached 45-second rollback restores every original disable flag.
set -eu
trial=/run/lynx/wfi-fallback-trial
mkdir "$trial"  # Refuse overlapping/repeated trials on this boot.
for cpu in /sys/devices/system/cpu/cpu[0-9]*; do
    [ "$(cat "$cpu/cpuidle/state0/name")" = WFI ]
    [ "$(cat "$cpu/cpuidle/state0/disable")" = 0 ]
    for state in "$cpu"/cpuidle/state*; do
        [ -d "$state" ] || continue
        case "$state" in */state0) continue;; esac
        value=$(cat "$state/disable")
        case "$value" in 0|1) ;; *) exit 1;; esac
        printf '%s %s\n' "$state/disable" "$value" >> "$trial/original-flags"
    done
done
[ -s "$trial/original-flags" ]
cat > "$trial/restore.sh" <<'RESTORE'
#!/bin/sh
set -eu
if [ "${1:-}" != --now ]; then sleep 45; fi
while read -r path value; do
    case "$path" in /sys/devices/system/cpu/cpu[0-9]*/cpuidle/state[1-9]*/disable) ;; *) exit 1;; esac
    case "$value" in 0|1) ;; *) exit 1;; esac
    printf '%s\n' "$value" > "$path"
done < /run/lynx/wfi-fallback-trial/original-flags
echo WFI_TRIAL_ORIGINAL_FLAGS_RESTORED
RESTORE
restore() { sh "$trial/restore.sh" --now; }
trap restore EXIT
trap 'exit 1' HUP INT TERM
nohup sh "$trial/restore.sh" > "$trial/rollback.log" 2>&1 < /dev/null &
echo "$!" > "$trial/rollback.pid"
kill -0 "$(cat "$trial/rollback.pid")"
snapshot() {
    echo "SNAPSHOT $1"
    cat /proc/uptime /run/lynx/battery-last
    for cpu in /sys/devices/system/cpu/cpu[0-9]*; do
        for state in "$cpu"/cpuidle/state*; do
            [ -d "$state" ] || continue
            printf '%s ' "$state"
            for field in name disable usage time rejected; do
                printf '%s=' "$field"
                tr '\n' ' ' < "$state/$field"
            done
            echo
        done
    done
    tail -n 1 /run/lynx/thermal-watch.log /run/lynx/battery-watch.log
}
snapshot BEFORE
while read -r path value; do printf '1\n' > "$path"; done < "$trial/original-flags"
snapshot WFI_START
sleep 10
snapshot WFI_10_SECONDS
sleep 10
snapshot WFI_20_SECONDS
sleep 10
snapshot WFI_30_SECONDS
restore
trap - EXIT
snapshot RESTORED
