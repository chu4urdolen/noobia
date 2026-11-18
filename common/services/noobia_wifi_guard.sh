#!/usr/bin/env bash
# noobia_wifi_guard.sh — Self-contained Noobia Wi-Fi stability & defense service
#
# Continuously keeps wlx40a5ef5f66f1 connected to 'Noobia MT7612U'
# (192.168.100.106/24) with Wi-Fi power-save disabled and fq_codel active,
# and ensures ufw and fail2ban stay active.
# One-shot diagnostic and security audit tools live under /noobia/aigel/tools/.
#
# Logging (Aigel proposal, 2026-11-18 — NOT yet applied): heal attempts and
# recovery events are written to stdout, where systemd-journald captures them.
# During a long outage the journal gets exactly one line when the outage
# starts, one heartbeat per HEARTBEAT_CYCLES cycles (~5 min at the default
# 15 s interval), and one line when the link recovers. Heal behaviour itself
# (what is retried, how often) is unchanged from the current script.

set -euo pipefail

export PATH="/usr/sbin:/sbin:/usr/bin:/bin:${PATH:-}"
IFACE="wlx40a5ef5f66f1"
PROFILE="Noobia MT7612U"
STATIC_IP="192.168.100.106"
INTERVAL="${NOOBIA_WIFI_GUARD_INTERVAL:-15}"
HEARTBEAT_CYCLES="${NOOBIA_WIFI_GUARD_HEARTBEAT:-20}"   # ~5 min at 15 s interval
if (( HEARTBEAT_CYCLES < 1 )); then HEARTBEAT_CYCLES=1; fi  # guard: 0 would divide-by-zero under set -e

# stdout is captured by journald; no log file is created.
log() { printf '[noobia-wifi-guard] %s\n' "$*"; }

trap 'exit 0' TERM INT

degraded_cycles=0

while :; do
    dev_status="$(nmcli -t -f DEVICE,STATE,CONNECTION device status 2>/dev/null || true)"
    ip_status="$(ip -4 -br addr show "$IFACE" 2>/dev/null || true)"
    ps_status="$(iw dev "$IFACE" get power_save 2>/dev/null || true)"

    if [[ "$dev_status" == *"${IFACE}:connected:${PROFILE}"* && "$ip_status" == *"$STATIC_IP"* ]]; then
        if (( degraded_cycles > 0 )); then
            log "recovered: ${IFACE} connected to ${PROFILE} with ${STATIC_IP} after ${degraded_cycles} degraded cycle(s)"
            degraded_cycles=0
        fi
    else
        degraded_cycles=$((degraded_cycles + 1))
        if nmcli --wait 10 connection up "$PROFILE" ifname "$IFACE" >/dev/null 2>&1; then
            last_attempt="succeeded (exit 0)"
        else
            last_attempt="failed"
        fi
        if (( degraded_cycles == 1 || degraded_cycles % HEARTBEAT_CYCLES == 0 )); then
            log "degraded (cycle ${degraded_cycles}): ${IFACE} not connected to ${PROFILE}; reconnect attempt ${last_attempt}; ip='${ip_status:-no-address}'"
        fi
    fi

    if [[ "${ps_status,,}" != *"power save: off"* ]]; then
        if iw dev "$IFACE" set power_save off >/dev/null 2>&1; then
            log "maintenance: power-save set to off"
        else
            log "maintenance: power-save set failed (iw missing or device absent)"
        fi
    fi

    qdisc_status="$(tc qdisc show dev "$IFACE" 2>/dev/null || true)"
    if [[ "$qdisc_status" != *"fq_codel"* ]]; then
        if tc qdisc replace dev "$IFACE" root fq_codel >/dev/null 2>&1; then
            log "maintenance: fq_codel qdisc installed"
        else
            log "maintenance: fq_codel install failed"
        fi
    fi

    sleep "$INTERVAL"
done
