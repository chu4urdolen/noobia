#!/usr/bin/env bash
# Control Argus's fan through the Raspberry Pi 5 fan header, not the Argon MCU.
set -euo pipefail

temp_path=${ARGUS_FAN_TEMP_PATH:-/sys/class/thermal/thermal_zone0/temp}
cooling_dir=/sys/class/thermal/cooling_device0
state_path=$cooling_dir/cur_state
start_millicelsius=40000
stop_millicelsius=35000
check_seconds=${ARGUS_FAN_CHECK_SECONDS:-60}
repeat_seconds=${ARGUS_FAN_REPEAT_SECONDS:-4}

if (( EUID != 0 )); then
    printf 'This controller must run as root\n' >&2
    exit 1
fi
if [[ ! $check_seconds =~ ^[1-9][0-9]*$ || ! $repeat_seconds =~ ^[1-9][0-9]*$ ]]; then
    printf 'Check and repeat periods must be positive integer seconds\n' >&2
    exit 1
fi
if [[ ! -r $cooling_dir/type || $(<"$cooling_dir/type") != pwm-fan ]]; then
    printf 'cooling_device0 is not the Pi fan; refusing to start\n' >&2
    exit 1
fi

max_state=$(<"$cooling_dir/max_state")
if (( max_state < 1 )); then
    printf 'Fan has no usable on state\n' >&2
    exit 1
fi

fan_on=0
stop_fan() {
    printf '0\n' > "$state_path"
    printf 'Fan controller stopped; Pi fan returned to idle\n'
}
trap stop_fan EXIT

# A fresh start is off unless the first temperature reading reaches 40 C.
printf '0\n' > "$state_path"
next_check=0
while true; do
    if (( SECONDS >= next_check )); then
        temperature=$(<"$temp_path")
        if [[ ! $temperature =~ ^[0-9]+$ ]]; then
            printf 'Invalid CPU temperature: %s\n' "$temperature" >&2
            exit 1
        fi

        if (( fan_on == 0 && temperature >= start_millicelsius )); then
            fan_on=1
            printf 'CPU %.1f C: fan on\n' "$((temperature / 1000))" >&2
        elif (( fan_on == 1 && temperature <= stop_millicelsius )); then
            fan_on=0
            printf '0\n' > "$state_path"
            printf 'CPU %.1f C: fan off\n' "$((temperature / 1000))" >&2
        fi
        next_check=$((SECONDS + check_seconds))
    fi

    if (( fan_on == 1 )); then
        printf '%s\n' "$max_state" > "$state_path"
    fi
    sleep "$repeat_seconds"
done
