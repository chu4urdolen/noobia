# Normal BusyBox netlink hotplug/firmware service; no automatic module commands.
lynx_firmware_events_start() {
    [ ! -e /run/lynx/mdev.pid ] || return 1
    if [ -e /etc/mdev.conf ] || [ -L /etc/mdev.conf ]; then
        [ -f /etc/mdev.conf ] && [ ! -L /etc/mdev.conf ] && [ ! -s /etc/mdev.conf ] || return 1
    fi
    $BB mdev -df -vv > /run/lynx/mdev.log 2>&1 &
    firmware_events_pid=$!
    printf '%s\n' "$firmware_events_pid" > /run/lynx/mdev.pid
    for firmware_events_try in 1 2 3 4 5; do
        if ! kill -0 "$firmware_events_pid"; then return 1; fi
        if $BB awk -v pid="$firmware_events_pid" '
            $2 == 15 && $3 == pid && length($4) == 8 && $4 !~ /[^0-9a-fA-F]/ && $4 ~ /[13579bBdDfF]$/ { count++ }
            END { exit (count == 1) ? 0 : 1 }
        ' /proc/net/netlink; then
            printf '%s\n' "pid=$firmware_events_pid netlink_protocol=15 group1=subscribed" > /run/lynx/firmware-events-ready
            log 'FIRMWARE_NETLINK_SERVICE_READY'
            return 0
        fi
        $BB sleep 1
    done
    kill "$firmware_events_pid" 2>/dev/null || true
    return 1
}
