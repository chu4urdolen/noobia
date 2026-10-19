#!/sbin/openrc-run
# Alpine adopts the current rescue-stage WLAN without restarting it. A later
# cold boot can start WPA/DHCP after the stock module/bootstrap stage.
description="Lynx Noobia WLAN association and DHCP"

depend() {
    need lynx-health
    before lynx-dropbear
}

wpa_running() {
    for proc in /proc/[0-9]*; do
        [ -r "$proc/comm" ] || continue
        [ "$(cat "$proc/comm")" = wpa_supplicant ] || continue
        case "$(tr '\000' ' ' < "$proc/cmdline")" in
            *' -i wlan0 '*) return 0 ;;
        esac
    done
    return 1
}

associated_with_address() {
    [ "$(cat /sys/class/net/wlan0/carrier 2>/dev/null)" = 1 ] || return 1
    /sbin/ip -4 addr show dev wlan0 | grep -Eq 'inet 192\.168\.100\.[0-9]+/24 '
}

start() {
    ebegin "Starting Lynx Alpine Wi-Fi"
    /bin/sh /run/lynx/lynx-health-supervisor.sh --once >/dev/null || {
        eend 1 "health supervisor not ready"; return 1;
    }
    [ -d /sys/class/net/wlan0 ] || { eend 1 "wlan0 absent"; return 1; }
    [ -s /etc/lynx/wpa_supplicant.conf ] || {
        eend 1 "private Wi-Fi config missing"; return 1;
    }
    if wpa_running; then
        associated_with_address || { eend 1 "existing WPA has no Noobia address"; return 1; }
        eend 0
        return 0
    fi
    [ ! -e /run/lynx/alpine-wpa.pid ] || {
        eend 1 "stale or foreign WPA pidfile"; return 1;
    }
    /sbin/ip link set wlan0 up || { eend 1 "wlan0 link up failed"; return 1; }
    /sbin/wpa_supplicant -B -D nl80211 -i wlan0 \
        -c /etc/lynx/wpa_supplicant.conf \
        -P /run/lynx/alpine-wpa.pid -f /run/lynx/alpine-wpa.log || {
        eend 1 "Alpine WPA failed to start"; return 1;
    }
    connected=0
    for attempt in $(seq 1 45); do
        if [ "$(cat /sys/class/net/wlan0/carrier 2>/dev/null)" = 1 ]; then
            connected=1; break
        fi
        sleep 1
    done
    [ "$connected" = 1 ] || { eend 1 "WPA association timed out"; return 1; }
    /sbin/udhcpc -n -q -t 6 -T 4 -i wlan0 -x hostname:lynx || {
        eend 1 "DHCP failed"; return 1;
    }
    wpa_running && associated_with_address || {
        eend 1 "Noobia WLAN postcheck failed"; return 1;
    }
    eend 0
}

status() {
    wpa_running && associated_with_address
}

stop() {
    ebegin "Stopping Lynx Alpine Wi-Fi"
    eend 1 "manual stop refused while rescue SSH may depend on WLAN"
    return 1
}
