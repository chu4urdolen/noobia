#!/bin/sh
# Offline V31 RAM candidate. --run preserves the host-confirmed trial.
# --run-local is for a future init-owned autonomous boot after the payload
# archive is verified. Neither mode changes the installed V19 image.
set -eu
BB=/bin/busybox
RUN=/run/lynx
PACK=${2:-}
GAUGE=/sys/bus/i2c/devices/7-0055

say() {
    printf 'LYNX_HEALTH_BOOT %s\n' "$*"
    printf '<6>LYNX_HEALTH_BOOT %s\n' "$*" > /dev/kmsg 2>/dev/null || true
}
fail() { say "FAILED $*"; exit 1; }

case "${1:-}" in
    --plan)
        printf '%s\n' preflight sensor-modules thermal-watch cpu-modules \
            gauge-identity battery-monitor battery-watch wfi-fallback \
            cooling-watch health-supervisor
        exit 0;;
    --run|--run-local) [ "$#" = 2 ] || fail 'use --run[-local] EXTRACTED_PACK';;
    *) fail 'use --plan or --run[-local] EXTRACTED_PACK';;
esac

token=$(cat /etc/lynx/session-token) || fail 'boot token unavailable'
case "$1" in
    --run)
        [ -f "$RUN/host-confirmed" ] || fail 'pinned host has not confirmed this boot'
        confirmed=$(cat "$RUN/host-confirmed") || fail 'host confirmation unavailable'
        [ -n "$token" ] && [ "$confirmed" = "$token" ] || fail 'host confirmation mismatch';;
    --run-local)
        [ -f "$RUN/local-boot-ready" ] || fail 'local init has not approved this boot'
        local_ready=$(cat "$RUN/local-boot-ready") || fail 'local init marker unavailable'
        [ -n "$token" ] && [ "$local_ready" = "$token" ] || fail 'local init marker mismatch'
        [ "$(cat "$RUN/bootstrap-result")" = 0 ] || fail 'stock bootstrap incomplete'
        offline_supplies=0
        for supply in /sys/class/power_supply/*; do
            [ -r "$supply/online" ] || continue
            online=$(cat "$supply/online") || fail 'charger state unreadable'
            [ "$online" = 0 ] || fail 'USB or charger is online; charging unvalidated'
            offline_supplies=$((offline_supplies+1))
        done
        [ "$offline_supplies" -ge 1 ] || fail 'no charger state available';;
esac
[ ! -e "$RUN/health-bootstrap" ] || fail 'bootstrap already attempted'
mkdir "$RUN/health-bootstrap" || fail 'cannot reserve bootstrap state'

# An independent timer is deliberately never cancelled on a failed step. If a
# kernel module probe blocks the child, this timer still requests power-off.
( "$BB" sleep 180; say 'STARTUP_TIMEOUT_POWER_OFF'; "$BB" poweroff -f ) \
    > "$RUN/health-bootstrap/timer.log" 2>&1 < /dev/null &
timer=$!
printf '%s\n' "$timer" > "$RUN/health-bootstrap/timer.pid"

"$BB" sh /usr/libexec/lynx/autonomous-health-preflight.sh --check "$PACK" ||
    fail 'hardware preflight refused'

load_module() {
    name=$1 file=$2
    shift 2
    [ ! -e "/sys/module/$name" ] || fail "module already present: $name"
    say "INSMOD_BEGIN $name"
    "$BB" insmod "$PACK/modules/$file" "$@" || fail "module insertion failed: $name"
    [ -d "/sys/module/$name" ] || fail "module insertion returned without sysfs: $name"
    say "INSMOD_RETURNED $name"
}
install_script() {
    name=$1
    [ ! -e "$RUN/$name" ] || fail "script already installed: $name"
    "$BB" cp "$PACK/scripts/$name" "$RUN/$name" || fail "cannot install $name"
    "$BB" chmod 700 "$RUN/$name"
}
launch() {
    name=$1
    [ ! -e "$RUN/$name.pid" ] || fail "watcher already started: $name"
    "$BB" nohup "$BB" sh "$RUN/$name.sh" > "$RUN/$name.log" 2>&1 < /dev/null &
    pid=$!
    printf '%s\n' "$pid" > "$RUN/$name.pid"
    "$BB" sleep 1
    kill -0 "$pid" || fail "watcher exited: $name"
}

load_module nvmem_mtk_devinfo nvmem_mtk-devinfo.ko
load_module soc_temp_lvts soc_temp_lvts.ko
[ -r /sys/class/thermal/thermal_zone0/temp ] || fail 'SoC sensors unavailable'
. "$PACK/review/cpu-temperature-guard.sh" || fail 'thermal guard unavailable'
lynx_cpu_temperature_guard || fail 'sensor temperature guard refused'
install_script thermal-watch.sh
"$BB" touch "$RUN/thermal-watch.ready"
launch thermal-watch
"$BB" sh "$RUN/thermal-watch.sh" --once || fail 'thermal watcher sample refused'

load_module oplus_omrg oplus_omrg.ko
lynx_cpu_temperature_guard || fail 'CPU frequency temperature guard refused'
load_module mediatek_cpufreq_hw mediatek-cpufreq-hw.ko

# Repeat the same single DeviceType query used in the supervised handset trial.
lynx_cpu_temperature_guard || fail 'gauge temperature guard refused'
[ ! -e "$RUN/gauge-sample.started" ] || fail 'gauge query already attempted'
echo started > "$RUN/gauge-sample.started"
load_module lynx_gauge_sample lynx-gauge-sample.ko allow_identity_query=1
type=$("$BB" cat "$GAUGE/raw_device_type") || fail 'gauge identity unreadable'
case "$type" in 42495) ;; *) fail "unexpected gauge DeviceType: $type";; esac
"$BB" rmmod lynx_gauge_sample || fail 'identity probe did not unload'
[ ! -d /sys/module/lynx_gauge_sample ] || fail 'identity module remains loaded'
say "GAUGE_DEVICE_TYPE_CONFIRMED $type"

load_module lynx_battery_monitor lynx-battery-monitor.ko \
    allow_reads=1 confirmed_device_type=42495
"$BB" cat "$GAUGE/battery_snapshot" > "$RUN/health-bootstrap/first-battery" ||
    fail 'battery snapshot unavailable'
for field in temperature_error voltage_error current_error capacity_error; do
    "$BB" grep -Fxq "$field=0" "$RUN/health-bootstrap/first-battery" ||
        fail "battery sample error: $field"
done
"$BB" grep -Fxq 'gauge_device_type=42495' "$RUN/health-bootstrap/first-battery" ||
    fail 'battery snapshot identity mismatch'
temp=$("$BB" sed -n 's/^temperature_millidegrees_celsius=//p' "$RUN/health-bootstrap/first-battery")
capacity=$("$BB" sed -n 's/^capacity_percent=//p' "$RUN/health-bootstrap/first-battery")
case "$temp:$capacity" in *[!0-9:]*|'':*|*:'') fail 'invalid battery numbers';; esac
[ "$temp" -gt 0 ] && [ "$temp" -lt 35000 ] || fail 'battery too warm for startup'
[ "$capacity" -ge 20 ] && [ "$capacity" -le 100 ] || fail 'battery reserve too low'
install_script battery-watch.sh
"$BB" sh "$RUN/battery-watch.sh" --once || fail 'battery watcher first sample refused'
launch battery-watch

install_script wfi-fallback.sh
"$BB" sh "$RUN/wfi-fallback.sh" --apply > "$RUN/wfi-fallback-setup.log" 2>&1 ||
    fail 'safe WFI fallback refused'

install_script thermal-cooling-watch.sh
# Its tested startup guard requires every CPU/SoC reading below 40°C. Wait
# briefly for passive cooling. Launch only once, after a read-only check.
cooling_temperature_ready() {
    cpu=0 soc=0
    for zone in /sys/class/thermal/thermal_zone*; do
        [ -r "$zone/type" ] && [ -r "$zone/temp" ] || continue
        kind=$(cat "$zone/type") || return 1
        case "$kind" in soc_max) soc=$((soc+1));; cpu_*) cpu=$((cpu+1));; *) continue;; esac
        value=$(cat "$zone/temp") || return 1
        case "$value" in ''|*[!0-9]*) return 1;; esac
        [ "$value" -gt 0 ] && [ "$value" -lt 40000 ] || return 1
    done
    [ "$soc" -ge 1 ] && [ "$cpu" -ge 2 ]
}
cool_ready=0
for attempt in 1 2 3 4 5 6; do
    if cooling_temperature_ready; then
        cool_ready=1
        break
    fi
    say "COOLING_TEMPERATURE_WAIT attempt=$attempt"
    "$BB" sleep 10
done
[ "$cool_ready" = 1 ] || fail 'cooling temperature deadline exceeded'
# The watcher independently rechecks <40°C just before acquiring cooling
# controls. If the temperature rises between our check and its check, it
# exits before creating its state directory. Retry only that clean refusal.
# A live process or partial state is never restarted or overwritten.
cooling_started=0
for attempt in 1 2 3; do
    [ ! -e "$RUN/thermal-cooling-watch" ] || fail 'cooling startup already attempted'
    "$BB" nohup "$BB" sh "$RUN/thermal-cooling-watch.sh" --run \
        >> "$RUN/thermal-cooling-watch.log" 2>&1 < /dev/null &
    cooling_pid=$!
    "$BB" sleep 1
    if [ -r "$RUN/thermal-cooling-watch/pid" ] &&
       [ "$(cat "$RUN/thermal-cooling-watch/pid")" = "$cooling_pid" ] &&
       [ -f "$RUN/thermal-cooling-watch/ready" ] && kill -0 "$cooling_pid"; then
        cooling_started=1
        break
    fi
    kill -0 "$cooling_pid" 2>/dev/null && fail 'cooling watcher alive without ready marker'
    wait "$cooling_pid" 2>/dev/null || true
    [ ! -e "$RUN/thermal-cooling-watch" ] || fail 'cooling watcher left partial state'
    say "COOLING_WATCH_CLEAN_RETRY attempt=$attempt"
    [ "$attempt" = 3 ] || "$BB" sleep 5
done
[ "$cooling_started" = 1 ] || fail 'cooling watcher did not become ready'

install_script lynx-health-supervisor.sh
"$BB" sh "$RUN/lynx-health-supervisor.sh" --once || fail 'final health check refused'
"$BB" nohup "$BB" sh "$RUN/lynx-health-supervisor.sh" --watch \
    > "$RUN/health-supervisor.log" 2>&1 < /dev/null &
health_pid=$!
"$BB" sleep 1
[ -r "$RUN/health-supervisor/pid" ] &&
    [ "$(cat "$RUN/health-supervisor/pid")" = "$health_pid" ] &&
    kill -0 "$health_pid" || fail 'health supervisor did not become ready'
"$BB" sh "$RUN/lynx-health-supervisor.sh" --once || fail 'health supervisor postcheck refused'

kill "$timer" || fail 'startup timer cannot be cancelled'
wait "$timer" 2>/dev/null || true
echo ready > "$RUN/health-bootstrap/ready"
say 'READY_ON_PHONE_MONITORING_ACTIVE'
