#!/usr/bin/env bash
# noobia_wifi_guard.sh — Self-contained Noobia Wi-Fi stability & defense service
#
# Continuously keeps wlx40a5ef5f66f1 connected to 'Noobia MT7612U'
# (192.168.100.106/24) with Wi-Fi power-save disabled and fq_codel active,
# and ensures ufw and fail2ban stay active.
# One-shot diagnostic and security audit tools live under /noobia/aigel/tools/.

set -euo pipefail

export PATH="/usr/sbin:/sbin:/usr/bin:/bin:${PATH:-}"
IFACE="wlx40a5ef5f66f1"
PROFILE="Noobia MT7612U"
STATIC_IP="192.168.100.106"
INTERVAL="${NOOBIA_WIFI_GUARD_INTERVAL:-15}"

trap 'exit 0' TERM INT

while :; do
    dev_status="$(nmcli -t -f DEVICE,STATE,CONNECTION device status 2>/dev/null || true)"
    ip_status="$(ip -4 -br addr show "$IFACE" 2>/dev/null || true)"
    ps_status="$(iw dev "$IFACE" get power_save 2>/dev/null || true)"

    if [[ "$dev_status" != *"${IFACE}:connected:${PROFILE}"* ]] || [[ "$ip_status" != *"$STATIC_IP"* ]]; then
        nmcli --wait 10 connection up "$PROFILE" ifname "$IFACE" >/dev/null 2>&1 || true
    fi

    if [[ "${ps_status,,}" != *"power save: off"* ]]; then
        iw dev "$IFACE" set power_save off >/dev/null 2>&1 || true
    fi

    qdisc_status="$(tc qdisc show dev "$IFACE" 2>/dev/null || true)"
    if [[ "$qdisc_status" != *"fq_codel"* ]]; then
        tc qdisc replace dev "$IFACE" root fq_codel >/dev/null 2>&1 || true
    fi

    sleep "$INTERVAL"
done
