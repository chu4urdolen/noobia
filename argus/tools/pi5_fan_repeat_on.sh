#!/usr/bin/env bash
# Reassert the Raspberry Pi 5 fan's maximum cooling state at a chosen interval.
# Arguments: duration in seconds (0 means continuous), interval in seconds.
set -euo pipefail

state_path=/sys/class/thermal/cooling_device0/cur_state
cooling_dir=${state_path%/cur_state}

if (( EUID != 0 )); then
    printf 'Run as root: sudo %s [duration_seconds] [interval_seconds]\n' "$0" >&2
    exit 1
fi
if [[ ! -r "$cooling_dir/type" || $(<"$cooling_dir/type") != pwm-fan ]]; then
    printf 'cooling_device0 is not the Pi fan; refusing to write to it\n' >&2
    exit 1
fi

duration=${1:-0}
interval=${2:-1}
if [[ ! $duration =~ ^[0-9]+$ || ! $interval =~ ^[1-9][0-9]*$ ]]; then
    printf 'Duration must be a nonnegative integer and interval a positive integer\n' >&2
    exit 2
fi

max_state=$(<"$cooling_dir/max_state")
if (( max_state < 1 )); then
    printf 'Fan has no usable on state\n' >&2
    exit 1
fi

fan_rpm_path=
for hwmon in /sys/class/hwmon/hwmon*; do
    if [[ -r "$hwmon/name" && $(<"$hwmon/name") == pwmfan ]]; then
        fan_rpm_path=$hwmon/fan1_input
        break
    fi
done

stop_fan() {
    printf '0\n' > "$state_path"
    printf 'Fan returned to automatic idle state\n'
}
trap stop_fan EXIT

start=$SECONDS
while (( duration == 0 || SECONDS - start < duration )); do
    printf '%s\n' "$max_state" > "$state_path"
    rpm=unknown
    if [[ -r $fan_rpm_path ]]; then
        rpm=$(<"$fan_rpm_path")
    fi
    printf '%s commanded=%s state=%s rpm=%s\n' \
        "$(date +%T)" "$max_state" "$(<"$state_path")" "$rpm"
    sleep "$interval"
done
