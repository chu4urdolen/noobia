#!/bin/sh
# Bounded, non-stress test of existing kernel CPU cooling controls.
# Increase each current cooling state by one; never weaken an existing limit.
set -eu
base=/run/lynx/cooling-control-trial
temp=$(cat /sys/class/thermal/thermal_zone0/temp)
kind=$(cat /sys/class/thermal/thermal_zone0/type)
[ "$kind" = soc_max ]
case "$temp" in ''|*[!0-9]*) exit 1;; esac
[ "$temp" -gt 0 ] && [ "$temp" -lt 45000 ]
for pidfile in /run/lynx/thermal-watch.pid /run/lynx/battery-watch.pid; do
    kill -0 "$(cat "$pidfile")"
done
mkdir "$base"
count=0
for dev in /sys/class/thermal/cooling_device*; do
    kind=$(cat "$dev/type")
    case "$kind" in thermal-cpufreq-[0-2]) ;; *) continue;; esac
    original=$(cat "$dev/cur_state")
    maximum=$(cat "$dev/max_state")
    case "$original:$maximum" in *[!0-9:]*) exit 1;; esac
    [ "$original" -lt "$maximum" ]
    printf '%s %s %s\n' "$dev/cur_state" "$original" "$((original + 1))" >> "$base/original-states"
    count=$((count + 1))
done
[ "$count" = 3 ]
cat > "$base/restore.sh" <<'RESTORE'
#!/bin/sh
set -eu
if [ "${1:-}" != --now ]; then sleep 30; fi
while read -r path original trial; do
    case "$path" in /sys/class/thermal/cooling_device[0-9]*/cur_state) ;; *) exit 1;; esac
    case "$original:$trial" in *[!0-9:]*) exit 1;; esac
    # Preserve an intervening controller's decision instead of overwriting it.
    actual=$(cat "$path")
    if [ "$actual" = "$trial" ]; then
        printf '%s\n' "$original" > "$path"
    elif [ "$actual" != "$original" ]; then
        echo "COOLING_RESTORE_SKIPPED_CONCURRENT_CHANGE $path $actual"
    fi
done < /run/lynx/cooling-control-trial/original-states
echo COOLING_TRIAL_RESTORE_COMPLETED
RESTORE
restore() { sh "$base/restore.sh" --now; }
trap restore EXIT
trap 'exit 1' HUP INT TERM
nohup sh "$base/restore.sh" > "$base/rollback.log" 2>&1 < /dev/null &
echo "$!" > "$base/rollback.pid"
kill -0 "$(cat "$base/rollback.pid")"
snapshot() {
    echo "SNAPSHOT $1"
    cat /proc/uptime /run/lynx/battery-last
    for policy in /sys/devices/system/cpu/cpufreq/policy*; do
        printf '%s scaling_max_freq=' "$policy"
        cat "$policy/scaling_max_freq"
    done
    while read -r path original trial; do printf '%s=' "$path"; cat "$path"; done < "$base/original-states"
    tail -n 1 /run/lynx/thermal-watch.log
}
snapshot BEFORE
while read -r path original trial; do printf '%s\n' "$trial" > "$path"; done < "$base/original-states"
sleep 1
snapshot LIMITED
sleep 10
snapshot LIMITED_10_SECONDS
restore
trap - EXIT
snapshot RESTORED
