#!/bin/sh
# Load Lynx's verified display and touch modules from Alpine's persistent root.
# Exact working V50 and V52 boot_a hashes gate display initialization.
set -eu

ROOT=/var/lib/lynx-display/modules
LIST=/var/lib/lynx-display/modules.list
V50_SHA=6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59
V52_SHA=9206aafb339ad66b2d942ea5795b8f476a5eaf3a148f9cdfc76be22cb83e30bf
KERNEL=5.10.149-android12-9-o-g311738fbb5a8
PANEL_MATCH=oplus22823_tm_nt37705_fhd_dsi_cmd-synaptics-s3910

verify_files() {
    [ "$(uname -r)" = "$KERNEL" ]
    [ -r "$LIST" ]
    [ -d "$ROOT" ]
    while read -r filename module digest; do
        [ -n "$filename" ] || continue
        case "$filename:$module:$digest" in
            *[!a-zA-Z0-9_.:-]*) echo "invalid module manifest entry" >&2; return 1 ;;
        esac
        [ -r "$ROOT/$filename" ] || { echo "missing $filename" >&2; return 1; }
        [ "$(sha256sum "$ROOT/$filename" | cut -c1-64)" = "$digest" ] || {
            echo "hash mismatch $filename" >&2
            return 1
        }
    done < "$LIST"
    [ "$(sha256sum /usr/local/bin/lynx-status-display | cut -c1-64)" = \
      "1a3d21bd40f5903377b800d0bb085443c0653a8c5ff30e1abb964e5eab0e2387" ]
    [ "$(sha256sum /usr/local/bin/lynx-portrait-display | cut -c1-64)" = \
      "656fa401e5d1c67fe94208d3d25a9af3761a3e513b92c19968662c3ecfb073f0" ]
    [ -x /usr/local/bin/lynx-displayctl ]
    [ -r /var/lib/lynx-display/frames/manifest.json ]
    [ -r /var/lib/lynx-display/frames.sha256 ]
    (cd /var/lib/lynx-display/frames && sha256sum -c \
      /var/lib/lynx-display/frames.sha256 >/dev/null)
}

require_working_boot() {
    boot_device=''
    for uevent in /sys/class/block/*/uevent; do
        grep -q '^PARTNAME=boot_a$' "$uevent" 2>/dev/null || continue
        [ -z "$boot_device" ] || { echo "duplicate boot_a device" >&2; return 1; }
        boot_device=/dev/$(basename "$(dirname "$uevent")")
    done
    [ -b "$boot_device" ] || { echo "boot_a device absent" >&2; return 1; }
    [ "$(cat /sys/class/block/$(basename "$boot_device")/size)" = 131072 ] || {
        echo "boot_a size mismatch" >&2
        return 1
    }
    boot_sha=$(sha256sum "$boot_device" | cut -c1-64)
    case "$boot_sha" in
        "$V50_SHA"|"$V52_SHA") ;;
        *) echo "boot_a is not a verified working V50/V52 image" >&2; return 1 ;;
    esac
}

check_hardware_health() {
    # A brief Wi-Fi or unrelated service transition must not abort a verified
    # module load halfway through the display stack. The service still checks
    # full Alpine health before and after startup.
    /usr/local/bin/lynx-status | /usr/bin/python3 -c '
import json, sys
s = json.load(sys.stdin)
b = s["battery"]
t = s["thermal"]["max_mC"]
ok = (b["gauge_type"] == 42495 and
      all(value == 0 for value in b["read_errors"].values()) and
      b["capacity_percent"] is not None and b["capacity_percent"] > 20 and
      b["temperature_mC"] is not None and 0 < b["temperature_mC"] < 40000 and
      t is not None and t < 55000 and
      s["root_filesystem"]["ext4_errors_count"] == 0)
if not ok:
    print("display hardware guard failed", file=sys.stderr)
sys.exit(0 if ok else 1)
'
}

load_modules() {
    while read -r filename module digest; do
        [ -n "$filename" ] || continue
        if grep -q "^$module " /proc/modules; then
            echo "already loaded: $module"
            continue
        fi
        if [ "$module" = oplus_bsp_tp_custom ]; then
            /bin/busybox timeout 20 /sbin/insmod "$ROOT/$filename" \
                "dsi_display0=$PANEL_MATCH"
        else
            /bin/busybox timeout 20 /sbin/insmod "$ROOT/$filename"
        fi
        grep -q "^$module " /proc/modules || {
            echo "module absent after load: $module" >&2
            return 1
        }
        echo "module present: $module"
        check_hardware_health
        echo "loaded: $module"
        if [ "$module" = oplus22823_tm_nt37705_fhd_dsi_cmd ] && \
           [ ! -L /sys/bus/platform/devices/14017000.dsi/driver ]; then
            printf '%s' 14017000.dsi > /sys/bus/platform/drivers/mtk-dsi/bind
            [ -c /dev/dri/card0 ]
        fi
    done < "$LIST"
}

status() {
    [ -c /dev/dri/card0 ]
    [ "$(cat /sys/class/drm/card0-DSI-1/status)" = connected ]
    [ "$(cat /sys/class/input/input0/name)" = touchpanel ]
    [ -c /dev/input/event0 ]
    /usr/local/bin/lynx-status --assert-ready >/dev/null
    echo "display and touch ready"
}

case "${1:-}" in
    --check-files) verify_files ;;
    --start)
        verify_files
        require_working_boot
        load_modules
        status
        ;;
    --status)
        require_working_boot
        status
        ;;
    *) echo "usage: $0 --check-files|--start|--status" >&2; exit 2 ;;
esac
