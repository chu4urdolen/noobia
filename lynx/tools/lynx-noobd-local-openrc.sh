#!/sbin/openrc-run
description="Lynx NRP/1 native function, sequencer, thread and VM endpoint"
command="/usr/bin/python3"
command_args="/usr/local/bin/lynx-noobd --host 192.168.100.107 --port 4243 --peer 192.168.100.106 --local-socket /run/lynx/noobd.sock"
command_background="yes"
pidfile="/run/lynx/noobd.pid"
output_log="/var/log/lynx-noobd.log"
error_log="/var/log/lynx-noobd.log"

depend() {
    need lynx-wifi lynx-media
    after lynx-display lynx-haptic
}
