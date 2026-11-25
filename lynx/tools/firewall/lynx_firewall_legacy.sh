#!/bin/sh
# Runtime-only legacy netfilter guard. No service or boot hook.
set -eu

IPT=${LYNX_IPTABLES:-iptables-legacy}
IP6T=${LYNX_IP6TABLES:-ip6tables-legacy}
STATE=${LYNX_FIREWALL_STATE:-/run/lynx-firewall-legacy}
DELAY=${LYNX_FIREWALL_DELAY:-120}
CHAIN=LYNX_GUARD
SCRIPT=$0

locked() {
    mkdir -p "$STATE"
    chmod 700 "$STATE"
    exec 9>"$STATE/lock"
    flock -x 9
}

# Never flush INPUT or change its policy. Only our own jump and chain move.
remove_own() {
    for tool in "$IPT" "$IP6T"; do
        while "$tool" -w 2 -C INPUT -j "$CHAIN" >/dev/null 2>&1; do
            "$tool" -w 2 -D INPUT -j "$CHAIN" || break
        done
        "$tool" -w 2 -F "$CHAIN" >/dev/null 2>&1 || true
        "$tool" -w 2 -X "$CHAIN" >/dev/null 2>&1 || true
    done
}

case ${1:-} in
  enable)
    locked
    command -v "$IPT" >/dev/null
    command -v "$IP6T" >/dev/null
    command -v nohup >/dev/null
    if "$IPT" -w 2 -nL "$CHAIN" >/dev/null 2>&1 ||
       "$IP6T" -w 2 -nL "$CHAIN" >/dev/null 2>&1 ||
       test -f "$STATE/pending"; then
        echo 'existing guard or rollback pending; refuse to replace' >&2
        exit 1
    fi
    token="$(date +%s)-$$"
    printf '%s\n' "$token" > "$STATE/pending"
    nohup /bin/sh "$SCRIPT" _rollback "$token" 9>&- </dev/null >/dev/null 2>&1 &
    echo "$!" > "$STATE/timer.pid"
    if ! (
        # Explicit exits are required: set -e is ignored inside an if condition.
        "$IPT" -w 2 -N "$CHAIN" || exit 1
        "$IP6T" -w 2 -N "$CHAIN" || exit 1
        "$IPT" -w 2 -A "$CHAIN" -i lo -j ACCEPT || exit 1
        "$IPT" -w 2 -A "$CHAIN" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT || exit 1
        "$IPT" -w 2 -A "$CHAIN" -i wlan0 -s 192.168.100.0/24 -p tcp -m multiport --dports 22,2222 -j ACCEPT || exit 1
        "$IPT" -w 2 -A "$CHAIN" -i wlan0 -s 192.168.100.106 -p tcp --dport 4243 -j ACCEPT || exit 1
        "$IPT" -w 2 -A "$CHAIN" -i wlan0 -p udp --sport 67 --dport 68 -j ACCEPT || exit 1
        "$IPT" -w 2 -A "$CHAIN" -i wlan0 -s 192.168.100.0/24 -p udp -m multiport --sports 5353,1900 -j ACCEPT || exit 1
        "$IPT" -w 2 -A "$CHAIN" -i wlan0 -p icmp --icmp-type echo-request -j ACCEPT || exit 1
        "$IPT" -w 2 -A "$CHAIN" -j DROP || exit 1
        "$IP6T" -w 2 -A "$CHAIN" -i lo -j ACCEPT || exit 1
        "$IP6T" -w 2 -A "$CHAIN" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT || exit 1
        "$IP6T" -w 2 -A "$CHAIN" -i wlan0 -p udp --sport 547 --dport 546 -j ACCEPT || exit 1
        "$IP6T" -w 2 -A "$CHAIN" -i wlan0 -p ipv6-icmp -j ACCEPT || exit 1
        "$IP6T" -w 2 -A "$CHAIN" -j DROP || exit 1
        "$IPT" -w 2 -I INPUT 1 -j "$CHAIN" || exit 1
        "$IP6T" -w 2 -I INPUT 1 -j "$CHAIN" || exit 1
    ); then
        remove_own
        rm -f "$STATE/pending" "$STATE/timer.pid"
        echo 'rule insertion failed; own chains removed' >&2
        exit 1
    fi
    echo "loaded; auto-revert in ${DELAY}s unless confirmed"
    ;;
  _rollback)
    sleep "$DELAY"
    exec /bin/sh "$SCRIPT" _rollback_locked "${2:-}"
    ;;
  _rollback_locked)
    locked
    if test -f "$STATE/pending" && test "$(cat "$STATE/pending")" = "${2:-}"; then
        remove_own
        rm -f "$STATE/pending" "$STATE/timer.pid"
    fi
    ;;
  confirm)
    locked
    test -f "$STATE/pending" || { echo 'no pending rule set' >&2; exit 1; }
    "$IPT" -w 2 -C INPUT -j "$CHAIN"
    "$IP6T" -w 2 -C INPUT -j "$CHAIN"
    rm -f "$STATE/pending" "$STATE/timer.pid"
    echo 'confirmed; runtime rules retained until disable or reboot'
    ;;
  disable)
    locked
    remove_own
    rm -f "$STATE/pending" "$STATE/timer.pid"
    echo 'legacy guard removed'
    ;;
  status)
    if "$IPT" -w 2 -C INPUT -j "$CHAIN" >/dev/null 2>&1 &&
       "$IP6T" -w 2 -C INPUT -j "$CHAIN" >/dev/null 2>&1; then
        if test -f "$STATE/pending"; then echo pending; else echo active; fi
    else
        echo off
    fi
    ;;
  *) echo 'usage: lynx_firewall_legacy.sh enable|confirm|disable|status' >&2; exit 2 ;;
esac
