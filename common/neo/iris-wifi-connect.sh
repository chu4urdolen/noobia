#!/bin/sh
set -eu

# This controls the ESP32-S3 dongle over its USB CDC console. No password is
# printed or passed as a process argument to another program.
config=${IRIS_WIFI_CONFIG:-/etc/iris-wifi.conf}
port=${IRIS_CDC_PORT:-/dev/ttyACM0}

[ -r "$config" ] || { echo "missing Wi-Fi config: $config" >&2; exit 1; }
[ -c "$port" ] || { echo "missing Iris CDC port: $port" >&2; exit 1; }
. "$config"
: "${IRIS_WIFI_SSID:?missing IRIS_WIFI_SSID}"
: "${IRIS_WIFI_PASSWORD:?missing IRIS_WIFI_PASSWORD}"

# The upstream CLI separates fields at spaces; reject unsupported values.
case "$IRIS_WIFI_SSID:$IRIS_WIFI_PASSWORD" in
  *[!a-zA-Z0-9_.:-]*) echo 'SSID/password contains unsupported CLI characters' >&2; exit 1 ;;
esac

stty -F "$port" 115200 raw -echo -hupcl
sleep 2
printf 'sta -s %s -p %s\n' "$IRIS_WIFI_SSID" "$IRIS_WIFI_PASSWORD" > "$port"
echo 'Iris Wi-Fi connection requested'
