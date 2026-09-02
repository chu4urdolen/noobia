#!/usr/bin/env bash
set -euo pipefail
if (( $# < 4 )); then
  echo "usage: $0 BLUETOOTHCTL_PID NOTIFY_FD SEQUENCE OUTPUT.jpg" >&2
  exit 2
fi
bridge_pid=$1; notify_fd=$2; sequence=$3; output=$4
offset=0; part="${output}.part"; scratch=$(mktemp)
trap "rm -f \"$scratch\"" EXIT
[[ $sequence =~ ^[0-9]+$ ]] || { echo "invalid sequence" >&2; exit 2; }
[[ -n ${NOOB_BLE_LOG:-} ]] ||
  { echo "set NOOB_BLE_LOG to the bridge transcript" >&2; exit 2; }
if (( EUID != 0 )); then
  exec pkexec env NOOB_BLE_LOG="$NOOB_BLE_LOG" "$0" "$@"
fi
: > "$part"
request=0
while :; do
  request=$((request + 1)); request_id="fetch${request}"
  before=$(stat -c %s "$NOOB_BLE_LOG")
  /noobia/iris/tools/noob_ble_fd "$bridge_pid" "$notify_fd" \
    "NRP/1 $request_id CALL SD_READ_CHUNK $sequence $offset 32" >/dev/null
  found=
  for _ in $(seq 1 100); do
    tail -c "+$((before + 1))" "$NOOB_BLE_LOG" > "$scratch"
    hex=$(sed -n "s/.*#   \\(\\([0-9a-f][0-9a-f] \\)\\{1,16\\}\\).*/\\1/p" \
      "$scratch" | tr -d " \\r\\n")
    response=$(printf "%s" "$hex" | xxd -r -p 2>/dev/null || true)
    [[ $response == *"NRP/1 $request_id OK"* &&
       $response == *" eof="* ]] && { found=1; break; }
    sleep 0.1
  done
  [[ -n $found ]] || { echo "BLE reply timeout" >&2; exit 1; }
  response=${response#*"NRP/1 $request_id OK "}
  data=$(sed -n "s/.* data=\\([0-9A-F]*\\) eof=.*/\\1/p" <<< "$response")
  next=$(sed -n "s/.*value=\\([0-9]*\\).*/\\1/p" <<< "$response")
  total=$(sed -n "s/.* size=\\([0-9]*\\).*/\\1/p" <<< "$response")
  eof=$(sed -n "s/.* eof=\\([01]\\).*/\\1/p" <<< "$response")
  [[ -n $next && -n $total && -n $eof ]] ||
    { echo "malformed Iris reply: $response" >&2; exit 1; }
  printf "%s" "$data" | xxd -r -p >> "$part"
  offset=$next; printf "\\rfetched %d/%d bytes" "$offset" "$total" >&2
  [[ $eof == 1 ]] && break
done
echo >&2
actual=$(stat -c %s "$part")
(( actual == total )) || { echo "size mismatch: $actual != $total" >&2; exit 1; }
mv "$part" "$output"
sha256sum "$output"
