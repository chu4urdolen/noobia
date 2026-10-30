#!/sbin/openrc-run
description="Lynx V52 Bluetooth transport and read-only Noobian GATT service"
command="/usr/bin/unshare"
command_args="-m -- /usr/bin/python3 /usr/local/bin/lynx-bluetoothd"
command_background="yes"
pidfile="/run/lynx/bluetoothd.pid"
output_log="/var/log/lynx-bluetoothd.log"
error_log="/var/log/lynx-bluetoothd.log"

depend() {
    need lynx-wifi lynx-noobd
    after lynx-display
}
