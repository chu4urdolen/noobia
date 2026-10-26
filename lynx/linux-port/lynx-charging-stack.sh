#!/bin/sh
# Load only the four matching stock modules proven on Lynx V50.
# No charger register, current limit, boot partition, or recovery writes.
set -eu

ROOT=/usr/local/lib/lynx-charging/modules
CHARGER=/sys/class/power_supply/11e01000.i2c:mt6375@34:chg
KERNEL=5.10.149-android12-9-o-g311738fbb5a8

module_loaded() {
    grep -q "^$1 " /proc/modules
}

module_file() {
    module_path=$ROOT/$1.ko
    [ -r "$module_path" ] || { echo "missing $module_path" >&2; return 1; }
    [ "$(sha256sum "$module_path" | cut -c1-64)" = "$2" ] || {
        echo "hash mismatch: $module_path" >&2
        return 1
    }
}

require_topology() {
    [ "$(uname -r)" = "$KERNEL" ]
    [ -d /sys/bus/platform/devices/11e43000.usb-phy0 ]
    [ -d /sys/bus/platform/devices/11e01000.i2c:mt6375@34:tcpc ]
    [ -d /sys/bus/platform/devices/mtk_ctd ]
    [ -d "$CHARGER" ]
    module_loaded tcpc_class
    module_loaded pd_dbg_info
}

load_once() {
    module_filename=$1
    module_name=$2
    module_hash=$3
    module_file "$module_filename" "$module_hash"
    if module_loaded "$module_name"; then
        echo "already loaded: $module_name"
    else
        /bin/busybox timeout 15 /sbin/insmod "$ROOT/$module_filename.ko"
        module_loaded "$module_name" || { echo "module absent after load: $module_name" >&2; return 1; }
        echo "loaded: $module_name"
    fi
}

status() {
    module_loaded phy_mtk_xsphy
    module_loaded tcpc_mt6375
    module_loaded mtk_chg_type_det
    module_loaded tcpci_late_sync
    [ -L /sys/bus/platform/devices/11e43000.usb-phy0/driver ]
    [ -L /sys/bus/platform/devices/11e01000.i2c:mt6375@34:tcpc/driver ]
    [ -L /sys/bus/platform/devices/mtk_ctd/driver ]
    [ -d /sys/class/tcpc/type_c_port0 ]
    echo "charging stack ready; attach=$(cat "$CHARGER/online"); type=$(cat "$CHARGER/usb_type")"
}

case "${1:-}" in
    --start)
        require_topology
        load_once phy-mtk-xsphy phy_mtk_xsphy d83486fe2a36bc122c107117851dfbc790f87440cd301720762be99299468f69
        load_once tcpc_mt6375 tcpc_mt6375 91f06878fc510103c0d22c0587297321d24833ac1ccddfe99885247e300e4e5e
        load_once mtk_chg_type_det mtk_chg_type_det e5d424193c78f1d051573d06c21a76eb7d9b5df776d4175aa3313d17428f70ab
        load_once tcpci_late_sync tcpci_late_sync 2c18ff5fa172c851599aec0a154f89b0a89c75f904262f9124674565769597f9
        status
        ;;
    --status)
        require_topology
        status
        ;;
    *) echo "usage: $0 --start|--status" >&2; exit 2 ;;
esac
