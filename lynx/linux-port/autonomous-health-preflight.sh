#!/bin/sh
# Read-only gate for a future self-starting health stage. This script neither
# inserts modules nor touches power policy. The caller must verify the archive
# hash before extraction and run this gate before loading the reviewed drivers.
set -eu
BB=/bin/busybox
PACK=${2:-}
SYS=/sys
DT=$SYS/firmware/devicetree/base
EXPECTED_KERNEL=5.10.149-android12-9-o-g311738fbb5a8

fail() { echo "LYNX_HEALTH_PREFLIGHT_REFUSED $*" >&2; exit 1; }

[ "${1:-}" = --check ] && [ "$#" = 2 ] || fail 'use --check EXTRACTED_PACK'
case "$PACK" in /*) ;; *) fail 'pack path must be absolute';; esac
[ -d "$PACK/review" ] && [ -d "$PACK/modules" ] || fail 'pack contents missing'
[ "$("$BB" uname -r)" = "$EXPECTED_KERNEL" ] || fail 'kernel release differs'

# The compact archive omits these stock modules because the successful V19
# Wi-Fi/bootstrap sequence loaded them first. A different boot must prove that
# same condition rather than assuming it.
for name in clk_mt6983 reset_ti_syscon oplus_project oplusboot buildvariant mtk_boot_common; do
    [ -d "$SYS/module/$name" ] || fail "stock prerequisite absent: $name"
done

(cd "$DT" && "$BB" sha256sum -c "$PACK/review/DT-SHA256SUMS") >/dev/null ||
    fail 'device tree differs from reviewed stock boot'
while IFS= read -r prop; do
    [ -n "$prop" ] || continue
    case "$prop" in /*|*..*) fail 'invalid absent-property path';; esac
    [ ! -e "$DT/$prop" ] || fail "unexpected device-tree property: $prop"
done < "$PACK/review/DT-ABSENT"

tag=$DT/chosen/atag,devinfo
[ -r "$tag" ] || tag=$DT/chosen@0/atag,devinfo
[ -r "$tag" ] || fail 'bootloader calibration tag absent'
count=$("$BB" od -An -N4 -tu4 "$tag") || fail 'calibration count unreadable'
count=$(printf '%s' "$count" | "$BB" tr -d ' \n')
case "$count" in ''|*[!0-9]*) fail 'invalid calibration count';; esac
[ "$count" -gt 0 ] && [ "$count" -le 400 ] || fail 'calibration count out of range'
total=$("$BB" wc -c < "$tag") || fail 'calibration size unreadable'
IFS= read -r minimum < "$PACK/review/DEVINFO-MIN-BYTES" || fail 'minimum calibration size absent'
case "$minimum" in ''|*[!0-9]*) fail 'invalid calibration minimum';; esac
[ "$total" -ge "$((4+count*4))" ] && [ "$((count*4))" -ge "$minimum" ] ||
    fail 'calibration tag truncated'

gauge=$SYS/bus/i2c/devices/7-0055
[ "$("$BB" cat "$gauge/name")" = bq27541-battery ] || fail 'gauge topology differs'
[ ! -e "$gauge/driver" ] && [ ! -L "$gauge/driver" ] || fail 'gauge already bound'
[ -e "$gauge/of_node/qcom,batt_bq28z610" ] || fail 'gauge device-tree marker absent'

for name in nvmem_mtk-devinfo.ko soc_temp_lvts.ko oplus_omrg.ko mediatek-cpufreq-hw.ko \
            lynx-gauge-sample.ko lynx-battery-monitor.ko; do
    [ -r "$PACK/modules/$name" ] || fail "packed module absent: $name"
done

echo LYNX_HEALTH_PREFLIGHT_PASS
