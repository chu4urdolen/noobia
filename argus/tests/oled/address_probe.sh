#!/bin/bash
# Safe SH1107 wiring test for an OLED connected to Argus's header I2C bus.
# It checks idle line levels and probes only the two usual OLED addresses.
# It deliberately sends no display initialization or framebuffer data.

set -u

BUS="${OLED_I2C_BUS:-1}"
TRIALS="${OLED_PROBE_TRIALS:-10}"
DELAY="${OLED_PROBE_DELAY:-0.1}"

cleanup() {
    sudo systemctl start argononed.service 2>/dev/null || true
}

# Argon's fan controller also uses this bus. Isolate it while probing, and
# always restore it even if this test is interrupted or an I2C command fails.
sudo systemctl stop argononed.service
trap cleanup EXIT INT TERM

echo "Idle GPIO state (GPIO2=SDA, GPIO3=SCL):"
pinctrl get 2
pinctrl get 3

for address in 0x3c 0x3d; do
    ack=0
    nack=0
    printf '%s trials: ' "$address"

    trial=1
    while [ "$trial" -le "$TRIALS" ]; do
        scan=$(sudo i2cdetect -y "$BUS" "$address" "$address" 2>/dev/null)
        short_address=${address#0x}
        if printf '%s\n' "$scan" | grep -qw "$short_address"; then
            printf 'A'
            ack=$((ack + 1))
        else
            printf 'N'
            nack=$((nack + 1))
        fi
        sleep "$DELAY"
        trial=$((trial + 1))
    done

    printf '  ACK=%s NACK=%s\n' "$ack" "$nack"
done

echo "Final GPIO state:"
pinctrl get 2
pinctrl get 3
