#!/sbin/openrc-run
# Alpine-owned SSH, bound only to Lynx's Noobia WLAN address on port 2222.
# Port 22 remains the BusyBox rescue connection during development.
description="Lynx Alpine SSH on the Noobia Wi-Fi network"

pidfile=/run/lynx/alpine-dropbear-2222.pid
keyfile=/etc/dropbear/lynx_ed25519_host_key
authorized=/root/.ssh/authorized_keys

depend() {
    need lynx-health
}

worker_is_ours() {
    [ -r "$pidfile" ] || return 1
    pid=$(cat "$pidfile") || return 1
    case "$pid" in ''|*[!0-9]*) return 1;; esac
    kill -0 "$pid" 2>/dev/null || return 1
    [ -r "/proc/$pid/cmdline" ] || return 1
    tr '\000' '\n' < "/proc/$pid/cmdline" | grep -Fx '/usr/sbin/dropbear' >/dev/null || return 1
    tr '\000' '\n' < "/proc/$pid/cmdline" | grep -Eq '^192\.168\.100\.[0-9]+:2222$' || return 1
}

noobia_address() {
    /sbin/ip -4 addr show dev wlan0 | sed -n 's/^[[:space:]]*inet \(192\.168\.100\.[0-9]*\)\/.*/\1/p' | head -n 1
}

start() {
    ebegin "Starting Lynx Alpine SSH"
    /bin/sh /run/lynx/lynx-health-supervisor.sh --once >/dev/null || {
        eend 1 "health supervisor not ready"; return 1;
    }
    [ -s "$keyfile" ] && [ -s "$authorized" ] || {
        eend 1 "SSH keys missing"; return 1;
    }
    if worker_is_ours; then
        eend 0
        return 0
    fi
    [ ! -e "$pidfile" ] || { eend 1 "stale or foreign SSH pidfile"; return 1; }
    address=$(noobia_address) || { eend 1 "WLAN address unavailable"; return 1; }
    [ -n "$address" ] || { eend 1 "Noobia WLAN address unavailable"; return 1; }
    /usr/sbin/dropbear -E -s -j -k -p "$address:2222" -P "$pidfile" -r "$keyfile" </dev/null >>/run/lynx/alpine-dropbear-2222.log 2>&1 || {
        eend 1 "Dropbear refused to start"; return 1;
    }
    sleep 1
    worker_is_ours || { eend 1 "Dropbear process not verified"; return 1; }
    eend 0
}

status() {
    worker_is_ours
}

stop() {
    ebegin "Stopping Lynx Alpine SSH"
    worker_is_ours || { eend 1 "SSH process identity refused"; return 1; }
    kill "$pid" || { eend 1 "SSH process did not stop"; return 1; }
    eend 0
}
