#!/bin/sh
# Runtime-only DNS-over-TLS proof. Never changes the system resolver.
set -eu

STATE=${LYNX_DNS_STATE:-/run/lynx-dns-trial}
CONFIG=${LYNX_DNS_CONFIG:-/usr/local/lib/noobia/dns/lynx-unbound-dot.conf}
UNBOUND=${LYNX_DNS_UNBOUND:-unbound}
CHECKCONF=${LYNX_DNS_CHECKCONF:-unbound-checkconf}
DELAY=${LYNX_DNS_DELAY:-120}
SCRIPT=$0

locked() {
    mkdir -p "$STATE"
    chmod 700 "$STATE"
    exec 9>"$STATE/lock"
    flock -x 9
}

stop_own() {
    if test -f "$STATE/unbound.pid"; then
        pid=$(cat "$STATE/unbound.pid")
        case $pid in *[!0-9]*|'') return 1;; esac
        if test -r "/proc/$pid/cmdline" &&
           tr '\0' ' ' < "/proc/$pid/cmdline" | grep -F -q -- "$CONFIG"; then
            kill -TERM "$pid" 2>/dev/null || true
        fi
    fi
}

restore_own() {
    stop_own || true
    rm -f "$STATE/pending" "$STATE/unbound.pid" "$STATE/timer.pid"
}

case ${1:-} in
  enable)
    locked
    test ! -f "$STATE/pending" || {
        echo 'DNS trial already present' >&2; exit 1; }
    test -f "$CONFIG"
    command -v "$UNBOUND" >/dev/null
    command -v "$CHECKCONF" >/dev/null
    "$CHECKCONF" "$CONFIG"
    nohup "$UNBOUND" -d -c "$CONFIG" 9>&- </dev/null >"$STATE/unbound.log" 2>&1 &
    echo "$!" > "$STATE/unbound.pid"
    if ! timeout 12 nslookup example.com 127.0.0.1 >/dev/null 2>&1; then
        restore_own
        echo 'local authenticated resolver did not answer' >&2
        exit 1
    fi
    token="$(date +%s)-$$"
    printf '%s\n' "$token" > "$STATE/pending"
    nohup /bin/sh "$SCRIPT" _rollback "$token" 9>&- </dev/null >/dev/null 2>&1 &
    echo "$!" > "$STATE/timer.pid"
    echo "local DoT proof active; auto-stop in ${DELAY}s"
    ;;
  _rollback)
    sleep "$DELAY"
    exec /bin/sh "$SCRIPT" _rollback_locked "${2:-}"
    ;;
  _rollback_locked)
    locked
    if test -f "$STATE/pending" && test "$(cat "$STATE/pending")" = "${2:-}"; then
        restore_own
    fi
    ;;
  disable)
    locked
    restore_own
    echo 'DNS trial removed'
    ;;
  status)
    if test -f "$STATE/pending"; then echo pending; else echo off; fi
    ;;
  *) echo 'usage: lynx_dns_trial.sh enable|disable|status' >&2; exit 2 ;;
esac
