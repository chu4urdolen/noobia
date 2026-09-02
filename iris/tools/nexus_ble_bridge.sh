#!/usr/bin/env bash
set -euo pipefail

SERVICE=6e6f6f62-6961-4e45-5855-530000000001
DOWNLINK=6e6f6f62-6961-4e45-5855-530000000002
UPLINK=6e6f6f62-6961-4e45-5855-530000000003
RUN_DIR=/noobia/iris/run
STATE="$RUN_DIR/ble-bridge.state"
LOG="$RUN_DIR/ble-bridge.log"
mkdir -p "$RUN_DIR"
: > "$LOG"

coproc BLUEZ { bluetoothctl; }
bridge_pid=$BLUEZ_PID
trap "kill $bridge_pid 2>/dev/null || true; rm -f \"$STATE\"" EXIT
socket_pid=
for _ in $(seq 1 50); do
  read -r socket_pid _ < "/proc/$bridge_pid/task/$bridge_pid/children" || true
  [[ -n $socket_pid ]] && break
  sleep 0.1
done
[[ -n $socket_pid ]] || { echo "could not locate bluetoothctl process" >&2; exit 1; }
printf "pid=%s\\nfd=\\nlog=%s\\n" "$socket_pid" "$LOG" > "$STATE"

{
  printf "menu gatt\\n"
  printf "register-service %s\\n" "$SERVICE"
  printf "yes\\n"
  printf "register-characteristic %s read,notify\\n" "$DOWNLINK"
  printf "00\\n"
  printf "register-characteristic %s write\\n" "$UPLINK"
  printf "00\\n"
  printf "register-application\\n"
} >&"${BLUEZ[1]}"

pkexec /usr/bin/btmgmt --index 0 add-adv -c -g 1
echo "Nexus BLE bridge active; waiting for Iris." | tee -a "$LOG"

# Mirror BlueZ output to a durable transcript. When Iris subscribes, publish
# the acquired socket descriptor so irisctl can send without process trivia.
while IFS= read -r line <&"${BLUEZ[0]}"; do
  printf "%s\\n" "$line" | tee -a "$LOG"
  if [[ $line == *"Notify sock acquired"* ]]; then
    notify_fd=
    for path in /proc/"$socket_pid"/fd/*; do
      target=$(readlink "$path" 2>/dev/null || true)
      [[ $target == socket:* ]] || continue
      candidate=${path##*/}
      (( candidate > ${notify_fd:-0} )) && notify_fd=$candidate
    done
    printf "pid=%s\\nfd=%s\\nlog=%s\\n" "$socket_pid" "$notify_fd" "$LOG" > "$STATE"
    echo "Iris channel ready: fd=$notify_fd" | tee -a "$LOG"
  fi
done
