#!/bin/sh
# Load Lynx's verified display and touch modules from Alpine's persistent root.
# The exact boot_a hash gates the untested V51 DSI cold-boot candidate.
set -eu

ROOT=/var/lib/lynx-display/modules
LIST=/var/lib/lynx-display/modules.list
V51_SHA=338f1280cbdc68e8896ff6b5ebb37fd79d0497280159ac35c962dd311f98847c
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
}

require_v51() {
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
    [ "$(sha256sum "$boot_device" | cut -c1-64)" = "$V51_SHA" ] || {
        echo "boot_a is not the exact V51 trial image" >&2
        return 1
    }
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
        /usr/local/bin/lynx-status --assert-ready >/dev/null
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
        require_v51
        load_modules
        status
        ;;
    --status)
        require_v51
        status
        ;;
    *) echo "usage: $0 --check-files|--start|--status" >&2; exit 2 ;;
esac
