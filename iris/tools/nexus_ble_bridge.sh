#!/usr/bin/env bash
set -euo pipefail

TOOLS=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
IRIS_ROOT=$(cd -- "$TOOLS/.." && pwd)
CONFIG=${IRIS_CONFIG_FILE:-"$TOOLS/iris-tools.conf"}
OPT_RUN_DIR=
while (( $# )); do
  case $1 in
    --config) CONFIG=$2; shift 2 ;;
    --run-dir) OPT_RUN_DIR=$2; shift 2 ;;
    --help|-h) echo "usage: $0 [--config FILE] [--run-dir DIR]"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done
[[ ! -r $CONFIG ]] || source "$CONFIG"
SERVICE=${IRIS_BLE_SERVICE_UUID:-6e6f6f62-6961-4e45-5855-530000000001}
DOWNLINK=${IRIS_BLE_DOWNLINK_UUID:-6e6f6f62-6961-4e45-5855-530000000002}
UPLINK=${IRIS_BLE_UPLINK_UUID:-6e6f6f62-6961-4e45-5855-530000000003}
RUN_DIR=${OPT_RUN_DIR:-${IRIS_RUN_DIR:-"$IRIS_ROOT/run"}}
STATE="$RUN_DIR/ble-bridge.state"
LOG="$RUN_DIR/ble-bridge.log"
mkdir -p "$RUN_DIR"
# Keep earlier diagnostic history.
touch "$LOG"
exec 9>"$RUN_DIR/ble-bridge.lock"
flock -n 9 || { echo "BLE bridge already running" >&2; exit 1; }

coproc BLUEZ { bluetoothctl; }
bridge_pid=$BLUEZ_PID
socket_pid=
cleanup() {
  [[ -z $socket_pid ]] || kill "$socket_pid" 2>/dev/null || true
  kill "$bridge_pid" 2>/dev/null || true
  rm -f "$STATE"
}
trap cleanup EXIT
trap 'exit 0' INT TERM
for _ in $(seq 1 50); do
  read -r socket_pid _ < "/proc/$bridge_pid/task/$bridge_pid/children" || true
  [[ -n $socket_pid ]] && break
  sleep 0.1
done
[[ -n $socket_pid ]] || { echo "could not locate bluetoothctl process" >&2; exit 1; }
printf "pid=%s\nfd=\nlog=%s\n" "$socket_pid" "$LOG" > "$STATE"

{
  printf "menu gatt\n"
  printf "register-service %s\n" "$SERVICE"
  printf "yes\n"
  printf "register-characteristic %s read,notify\n" "$DOWNLINK"
  printf "00\n"
  printf "register-characteristic %s write\n" "$UPLINK"
  printf "00\n"
  printf "register-application\n"
  printf "back\n"
  printf "advertise peripheral\n"
} >&"${BLUEZ[1]}"

echo "Nexus BLE bridge registering; waiting for Iris." | tee -a "$LOG"

# Mirror BlueZ output to a durable transcript. When Iris subscribes, publish
# the acquired socket descriptor so irisctl can send without process trivia.
while IFS= read -r line <&"${BLUEZ[0]}"; do
  printf "%s\n" "$line" | tee -a "$LOG"
  if [[ $line == *"Notify sock closed"* ]]; then
    printf "pid=%s\nfd=\nlog=%s\n" "$socket_pid" "$LOG" > "$STATE"
  fi
  if [[ $line == *"Notify sock acquired"* ]]; then
    notify_fd=
    for path in /proc/"$socket_pid"/fd/*; do
      target=$(readlink "$path" 2>/dev/null || true)
      [[ $target == socket:* ]] || continue
      candidate=${path##*/}
      (( candidate > ${notify_fd:-0} )) && notify_fd=$candidate
    done
    printf "pid=%s\nfd=%s\nlog=%s\n" "$socket_pid" "$notify_fd" "$LOG" > "$STATE"
    echo "Iris channel ready: fd=$notify_fd" | tee -a "$LOG"
  fi
done
