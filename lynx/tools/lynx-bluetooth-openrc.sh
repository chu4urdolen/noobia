#!/sbin/openrc-run
description="Lynx V52 authenticated Bluetooth Noobian transport"
supervisor="supervise-daemon"
command="/usr/bin/unshare"
command_args="-m -- /usr/bin/python3 /usr/local/bin/lynx-bluetoothd"
pidfile="/run/lynx/bluetoothd.pid"
respawn_delay=8
respawn_max=3
respawn_period=600
output_log="/var/log/lynx-bluetoothd.log"
error_log="/var/log/lynx-bluetoothd.log"

depend() {
    need lynx-wifi lynx-noobd
    after lynx-display
}

start_pre() {
    if [ -f /etc/lynx/bt-firstboot-trial ]; then
        mkdir -p /run/lynx/bt-firstboot-guard
        if [ -r /run/lynx/bt-firstboot-guard/pid ] &&
           kill -0 "$(cat /run/lynx/bt-firstboot-guard/pid)" 2>/dev/null; then
            return 0
        fi
        /usr/bin/setsid /bin/sh /usr/local/bin/lynx-bt-firstboot-guard \
            </dev/null >>/var/log/lynx-bt-firstboot-guard.log 2>&1 &
    fi
}
