#!/usr/bin/env bash
set -euo pipefail

# This file is also the fixture executable for both fixed command interfaces.
case ${1:-} in
  image) exit 0 ;;
  status) printf '%s\n' "$3"; exit 42 ;;
  --timeout)
    [[ ${SCENARIO:-} != offline ]] || exit 1
    case ${4:-$3} in
      SD_READ)
        bytes=$(tr -d '[:space:]' < "$(dirname "$0")/../../iris/programs/vm_police_on_all.hex")
        printf 'NRP/1 1 OK size=%d data=%s\n' "$(( ${#bytes} / 2 ))" "$bytes" ;;
      TEMP_HUMIDITY_READ) echo 'NRP/1 1 OK temperature_c=22.1 humidity_pct=61.0' ;;
      WIFI_STATUS)
        if [[ ${SCENARIO:-} == partial ]]; then exit 1; fi
        echo 'NRP/1 1 OK value=-72 detail=connected=1 configured=1 ip=192.168.100.8' ;;
      BLE_STATUS)
        if [[ ${SCENARIO:-} == partial ]]; then exit 1; fi
        echo 'NRP/1 1 OK value=1 detail=connected' ;;
      status) echo 'NRP/1 1 OK state=WAITING pc=135' ;;
      *) exit 2 ;;
    esac
    exit 0 ;;
esac

fixture=$(realpath "$0")
thread=$(dirname "$fixture")/../tools/thread_display
for scenario in connected offline partial; do
  status=0
  output=$(SCENARIO=$scenario NOOB_DISPLAY_CONFIG=/dev/null \
    NOOB_VM_CATALOG_DIR="$(dirname "$fixture")/../../iris/programs" \
    NOOB_DISPLAY_TOOL="$fixture" NOOB_ESP_CTL="$fixture" \
    bash "$thread" Iris_formatted.gif 5000) || status=$?
  [[ $status == 42 ]]
  case $scenario in
    connected)
      [[ $output == *$'IP 192.168.100.8\n22.1C 61% BLE:ON\npolice_all RUN'* ]] ;;
    offline)
      [[ $output == *'--C --% BLE:?'* && $output == *'ESP link unavailable'* ]]
      [[ $output != *'WiFi 192.'* ]] ;;
    partial)
      [[ $output == *'IP unavailable'* && $output == *'BLE:?'* ]]
      [[ $output != *'WiFi disconnected'* ]] ;;
  esac
done
echo 'status overlay: connected, missing USB and partial failures passed'
