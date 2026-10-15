#!/bin/sh
# Manual diagnostics after pinned SSH. Never sourced or run during boot.
BB=/bin/busybox
export PATH=/bin:/sbin:/usr/bin:/usr/sbin
PACK=$(CDPATH= cd -- "$("$BB" dirname "$0")" && pwd) || exit 1
fail() { printf 'THERMAL_REFUSED %s\n' "$*" >&2; exit 1; }
snapshot() {
    printf 'THERMAL_SNAPSHOT\n'
    "$BB" cat /proc/uptime /proc/loadavg
    for t in /sys/class/thermal/thermal_zone*; do
        [ -d "$t" ] || continue
        printf '%s ' "${t##*/}"
        "$BB" cat "$t/type" "$t/temp" 2>&1
    done
    for p in /sys/class/power_supply/*; do
        [ -d "$p" ] || continue
        printf 'SUPPLY %s\n' "${p##*/}"
        for a in type status online capacity temp health; do
            [ -r "$p/$a" ] || continue
            printf '%s=' "$a"; "$BB" cat "$p/$a" 2>&1
        done
    done
    for p in /sys/devices/system/cpu/cpufreq/policy*; do
        [ -d "$p" ] || continue
        printf 'CPU_POLICY %s\n' "${p##*/}"
        for a in scaling_governor scaling_cur_freq scaling_min_freq scaling_max_freq; do
            [ -r "$p/$a" ] || continue
            printf '%s=' "$a"; "$BB" cat "$p/$a" 2>&1
        done
    done
}
case "$#:$1" in
    0:|1:--inspect) snapshot; exit 0 ;;
    1:--plan) "$BB" cat "$PACK/manifest.json"; exit $? ;;
    2:--load) ;;
    *) fail 'use --inspect, --plan, or --load STAGE' ;;
esac
case "$2" in soc-temperature|cpu-frequency) stage=$2 ;; *) fail 'stage is review-only or unknown' ;; esac
[ ! -e "$PACK/REVIEW-HOLD" ] || fail 'pack is preparation-only; hardware review hold remains active'
"$BB" grep -qx "$stage" "$PACK/ALLOWED-STAGES" || fail 'stage is review-only or unknown'
[ -n "$SSH_CONNECTION" ] || fail 'a live SSH session is required'
[ "$("$BB" uname -r)" = '5.10.149-android12-9-o-g311738fbb5a8' ] || fail 'kernel mismatch'
IFS= read -r token < /etc/lynx/session-token || fail 'boot token unavailable'
IFS= read -r confirmed < /run/lynx/host-confirmed || fail 'pinned host has not confirmed this boot'
[ -n "$token" ] && [ "$confirmed" = "$token" ] || fail 'boot confirmation mismatch'
(cd "$PACK" && "$BB" sha256sum -c SHA256SUMS) || fail 'pack hash mismatch'
(cd /sys/firmware/devicetree/base && "$BB" sha256sum -c "$PACK/DT-SHA256SUMS") || fail 'device tree differs'
for name in clk_mt6983 reset_ti_syscon oplus_project; do
    [ -d "/sys/module/$name" ] || fail 'stock clock/reset/project prerequisites missing'
done
if [ "$stage" = soc-temperature ]; then
    tag=/sys/firmware/devicetree/base/chosen/atag,devinfo
    [ -r "$tag" ] || tag=/sys/firmware/devicetree/base/chosen@0/atag,devinfo
    [ -r "$tag" ] || fail 'bootloader calibration tag missing'
    count=$("$BB" od -An -N4 -tu4 "$tag") || fail 'calibration tag unreadable'
    count=$(printf '%s' "$count" | "$BB" tr -d ' \n')
    case "$count" in ''|*[!0-9]*) fail 'invalid calibration count' ;; esac
    [ "$count" -gt 0 ] && [ "$count" -le 400 ] || fail 'calibration count outside stock bounds'
    total=$("$BB" wc -c < "$tag") || fail 'calibration tag size unavailable'
    IFS= read -r minimum < "$PACK/DEVINFO-MIN-BYTES" || fail 'calibration bounds absent'
    [ "$total" -ge "$((4+count*4))" ] && [ "$((count*4))" -ge "$minimum" ] || fail 'truncated calibration tag'
fi
# Require a real SoC temperature before the CPU-frequency stage. This is a
# conservative test cutoff, not a validated battery-temperature guarantee.
if [ "$stage" = cpu-frequency ]; then
    found=0
    for p in /sys/class/thermal/thermal_zone*; do
        [ -r "$p/type" ] || continue
        IFS= read -r kind < "$p/type" || continue
        [ "$kind" = soc_max ] || continue
        IFS= read -r value < "$p/temp" || fail 'SoC temperature read failed'
        case "$value" in ''|*[!0-9]*) fail 'invalid SoC temperature' ;; esac
        [ "$value" -gt 0 ] && [ "$value" -lt 50000 ] || fail 'SoC outside conservative test range'
        found=1
    done
    [ "$found" = 1 ] || fail 'SoC temperature not available'
fi
"$BB" mkdir -p "$PACK/logs" || fail 'cannot create RAM logs'
[ ! -e "$PACK/logs/$stage.started" ] || fail 'stage already attempted; inspect logs before another attempt'
printf '%s\n' "$token" > "$PACK/logs/$stage.started" || exit 1
note() { printf '%s\n' "$*"; printf '%s\n' "$*" >> "$PACK/logs/$stage.log"; }
snapshot > "$PACK/logs/$stage.before" 2>&1
while IFS=' ' read -r name file; do
    case "$name:$file" in *..*|*/*|:*|*:) fail 'invalid module plan entry' ;; esac
    if [ -d "/sys/module/$name" ]; then note "ALREADY_LOADED $name"; continue; fi
    note "INSMOD_BEGIN $name"
    "$BB" insmod "$PACK/modules/$file" >> "$PACK/logs/$stage.log" 2>&1
    rc=$?
    note "INSMOD_RETURN $name status=$rc"
    [ "$rc" = 0 ] && [ -d "/sys/module/$name" ] || fail 'module insertion failed; no retry or automatic unload'
done < "$PACK/plans/$stage.list"
snapshot > "$PACK/logs/$stage.after" 2>&1
note "STAGE_INSERTIONS_RETURNED $stage; inspect sensor/binding results before proceeding"
