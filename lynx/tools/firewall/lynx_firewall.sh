#!/bin/sh
# Runtime-only Lynx firewall. No boot service; one table, removable without a reboot.
set -eu

RULES=${LYNX_FIREWALL_RULES:-/usr/local/lib/noobia/firewall/lynx_guard.nft}
STATE=${LYNX_FIREWALL_STATE:-/run/lynx-firewall}
NFT=${LYNX_FIREWALL_NFT:-nft}
DELAY=${LYNX_FIREWALL_DELAY:-120}
SCRIPT=$(command -v "$0")

# Serialize rule changes and confirmation so the timer cannot win a race at
# the confirmation boundary. The timer sleeps before taking this lock.
case ${1:-} in
  enable|confirm|disable|_rollback_locked)
    mkdir -p "$STATE"
    chmod 700 "$STATE"
    exec 9>"$STATE/lock"
    flock -x 9
    ;;
esac

case ${1:-} in
  enable)
    command -v "$NFT" >/dev/null || { echo 'nft unavailable' >&2; exit 1; }
    command -v nohup >/dev/null || { echo 'nohup unavailable' >&2; exit 1; }
    test -f "$RULES" || { echo 'rules missing' >&2; exit 1; }
    if "$NFT" list table inet lynx_guard >/dev/null 2>&1; then
      echo 'lynx_guard already loaded; refuse to replace' >&2; exit 1
    fi
    if test -f "$STATE/pending"; then
      echo 'rollback already pending' >&2; exit 1
    fi
    # A local timer survives loss of SSH. Never flush anyone else's tables.
    token="$(date +%s)-$$"
    printf '%s\n' "$token" > "$STATE/pending"
    nohup /bin/sh "$SCRIPT" _rollback "$token" 9>&- </dev/null >/dev/null 2>&1 &
    echo "$!" > "$STATE/timer.pid"
    if ! "$NFT" -f "$RULES"; then
      rm -f "$STATE/pending"
      "$NFT" delete table inet lynx_guard >/dev/null 2>&1 || true
      echo 'rules failed; own table removed' >&2; exit 1
    fi
    "$NFT" list table inet lynx_guard >/dev/null
    echo "loaded; auto-revert in ${DELAY}s unless confirmed"
    ;;
  _rollback)
    sleep "$DELAY"
    exec /bin/sh "$SCRIPT" _rollback_locked "${2:-}"
    ;;
  _rollback_locked)
    if test -f "$STATE/pending" && test "$(cat "$STATE/pending")" = "${2:-}"; then
      "$NFT" delete table inet lynx_guard >/dev/null 2>&1 || true
      rm -f "$STATE/pending" "$STATE/timer.pid"
    fi
    ;;
  confirm)
    test -f "$STATE/pending" || { echo 'no pending rule set' >&2; exit 1; }
    "$NFT" list table inet lynx_guard >/dev/null
    rm -f "$STATE/pending" "$STATE/timer.pid"
    echo 'confirmed; runtime rules retained until disable or reboot'
    ;;
  disable)
    rm -f "$STATE/pending" "$STATE/timer.pid"
    "$NFT" delete table inet lynx_guard >/dev/null 2>&1 || true
    echo 'lynx_guard removed'
    ;;
  status)
    if "$NFT" list table inet lynx_guard >/dev/null 2>&1; then
      if test -f "$STATE/pending"; then echo pending; else echo active; fi
    else
      echo off
    fi
    ;;
  *) echo 'usage: lynx_firewall.sh enable|confirm|disable|status' >&2; exit 2 ;;
esac
