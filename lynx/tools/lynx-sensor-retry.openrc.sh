#!/sbin/openrc-run
description="Retry Lynx audio and sensorhub after a low-charge boot"
command=/usr/bin/python3
command_args="/usr/local/bin/lynx-sensor-retry --watch"
command_background=true
pidfile=/run/lynx-sensor-retry.pid
output_log=/var/log/lynx-sensor-retry.log
error_log=/var/log/lynx-sensor-retry.log

depend() {
    need lynx-health lynx-battery-reserve
    after lynx-audio lynx-sensorhub lynx-local-logs
}
