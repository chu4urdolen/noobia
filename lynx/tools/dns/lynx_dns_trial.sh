#!/bin/sh
# Runtime-only DNS-over-TLS proof. Never changes the system resolver.
set -eu

STATE=${LYNX_DNS_STATE:-/run/lynx-dns-trial}
CONFIG=${LYNX_DNS_CONFIG:-/usr/local/lib/noobia/dns/lynx-unbound-dot.conf}
UNBOUND=${LYNX_DNS_UNBOUND:-unbound}
CHECKCONF=${LYNX_DNS_CHECKCONF:-unbound-checkconf}
DELAY=${LYNX_DNS_DELAY:-120}
PROC=${LYNX_DNS_PROC:-/proc}
DOT_PORT=${LYNX_DNS_DOT_PORT:-853}     # tests only; the phone always uses 853
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

# Evidence, not configuration (Dushich #543): the sockets of THIS unbound must show
# a connection to the DoT port and none to plain DNS port 53 away from loopback.
dot_proof() {
    pid=$1
    inodes=$(ls -l "$PROC/$pid/fd" 2>/dev/null | sed -n 's/.*socket:\[\([0-9]*\)\].*/\1/p' | tr '\n' ' ')
    dot_hex=$(printf '%04X' "$DOT_PORT")
    cat "$PROC/net/tcp" "$PROC/net/tcp6" "$PROC/net/udp" "$PROC/net/udp6" 2>/dev/null |
    awk -v inodes=" $inodes " -v dot="$dot_hex" '
        $1 ~ /^[0-9]+:$/ {
            n = split($3, r, ":"); port = r[n]; ip = r[1]; ino = $10
            mine = (ino != "0" && index(inodes, " " ino " ") > 0)
            loop = (ip == "0100007F" || ip == "00000000000000000000000001000000")
            if (mine && port == dot) d++
            if (mine && port == "0035" && !loop) p++
        }
        END { printf "dot=%d plain=%d\n", d, p; exit !(d > 0 && p == 0) }'
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
    # The timer starts before unbound, so an SSH drop right after this line
    # can never leave the proof running (Gwyn #531).
    token="$(date +%s)-$$"
    printf '%s\n' "$token" > "$STATE/pending"
    nohup /bin/sh "$SCRIPT" _rollback "$token" 9>&- </dev/null >/dev/null 2>&1 &
    echo "$!" > "$STATE/timer.pid"
    nohup "$UNBOUND" -d -c "$CONFIG" 9>&- </dev/null >"$STATE/unbound.log" 2>&1 &
    echo "$!" > "$STATE/unbound.pid"
    # Wait for the listener instead of failing on the first try (Gwyn #531).
    answered=0
    for i in 1 2 3 4 5 6; do
        if timeout 12 nslookup example.com 127.0.0.1 >/dev/null 2>&1; then answered=1; break; fi
        sleep 1
    done
    if [ "$answered" != 1 ]; then
        restore_own
        echo 'local authenticated resolver did not answer' >&2
        exit 1
    fi
    proven=0
    for i in 1 2 3 4 5 6; do      # the TLS connection may still be opening: up to ~3 s
        if proof=$(dot_proof "$(cat "$STATE/unbound.pid")"); then proven=1; break; fi
        sleep 0.5
    done
    if [ "$proven" != 1 ]; then
        restore_own
        echo "no proof of DNS over TLS ($proof): need a connection to port $DOT_PORT and none to port 53" >&2
        exit 1
    fi
    echo "local DoT proof active ($proof); auto-stop in ${DELAY}s"
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
