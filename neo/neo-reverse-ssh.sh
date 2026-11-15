#!/bin/bash
# Keep Neo reachable through Iris's USB-to-Wi-Fi link without exposing SSH on Wi-Fi.
set -u

source /home/noob/neo-tunnel.conf

# Cron may launch before USB DHCP is ready. flock also prevents duplicate loops.
exec 9>/home/noob/.ssh/noobia_tunnel.lock
flock -n 9 || exit 0

while true; do
    /usr/bin/ssh -N \
        -i /home/noob/.ssh/noobia_tunnel \
        -o BatchMode=yes \
        -o IdentitiesOnly=yes \
        -o StrictHostKeyChecking=yes \
        -o ExitOnForwardFailure=yes \
        -o ConnectTimeout=8 \
        -o ServerAliveInterval=15 \
        -o ServerAliveCountMax=3 \
        -b "$NEO_USB_ADDRESS" \
        -R "127.0.0.1:${NEXUS_REVERSE_PORT}:127.0.0.1:22" \
        "aria@${NEXUS_WIFI_ADDRESS}"
    logger -t neo-reverse-ssh 'tunnel disconnected; retrying in 15 seconds'
    sleep 15
done
