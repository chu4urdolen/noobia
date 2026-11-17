#!/bin/sh
# BusyBox udhcpc hook. Only RAM-backed Linux configuration is changed.
BB=/bin/busybox
set -f
case "$interface" in wlan0|wlan1) ;; *) exit 1 ;; esac
ipv4() {
    printf '%s\n' "$1" | $BB awk -F. 'NF!=4 {exit 1} {for(i=1;i<=4;i++) if($i !~ /^[0-9]+$/ || $i>255 || length($i)>3) exit 1}'
}
case "$1" in
    deconfig)
        $BB ifconfig "$interface" 0.0.0.0 || exit 1
        ;;
    bound|renew)
        ipv4 "$ip" && ipv4 "$subnet" || exit 1
        $BB ifconfig "$interface" "$ip" netmask "$subnet" up || exit 1
        for gateway in $router; do
            ipv4 "$gateway" || exit 1
            $BB ip route replace default via "$gateway" dev "$interface" || exit 1
            break
        done
        : > /etc/resolv.conf
        for server in $dns; do
            ipv4 "$server" || exit 1
            printf 'nameserver %s\n' "$server" >> /etc/resolv.conf
        done
        printf '%s\n' "$ip" > /run/lynx/address.tmp || exit 1
        $BB mv /run/lynx/address.tmp /run/lynx/address || exit 1
        printf 'LYNX_DHCP_BOUND interface=%s address=%s\n' "$interface" "$ip"
        ;;
    *) exit 1 ;;
esac
