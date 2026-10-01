# Iris as NanoPi USB Wi-Fi adapter

This was an earlier separate-firmware experiment, not the intended final
architecture. It replaced Iris's Noob/VM firmware and disabled BLE, so it was
rolled back. USB networking is now integrated with Iris's Noob/VM firmware in
`../firmware/iris_combined/`; this directory remains a reproducible reference
for the retired standalone experiment.

The experiment used the
ESP32-S3's **native USB-C port** (the connector without CH340/UART) for a
CDC-ECM network interface plus a CDC control console. The CH340/UART port is
used only to flash and restore firmware.

Source: Espressif `esp-iot-solution` USB dongle example at commit
`ee4719d17032261777f929bbaf1808817f269b61`, built with ESP-IDF 5.5.5 at
commit `b774170ff46c393eeb5e495ea37936038d3f4f4f`. Apply
[`credential-redaction.patch`](credential-redaction.patch) and
[`usb-ecm.patch`](usb-ecm.patch) to the upstream checkout. The first removes
password values from debug output; the second selects Linux ECM and CDC with
no USB Bluetooth. The local checkout and toolchain are ignored under
`neo/deps/`. [`sdkconfig.iris.defaults`](sdkconfig.iris.defaults) records the
same USB choices as a standalone override.

On 2026-09-28 the ECM image built successfully and was flashed to Iris through
`/dev/ttyUSB0` (ESP32-S3 MAC `30:ed:a0:0c:7e:98`). The complete 16 MiB image
from before flashing is at
`/noobia/iris/backups/iris-before-wifi-dongle-2026-09-28.bin`, SHA-256
`6b2dec05fcc4298d461a7833ee113402ff13772ff772b45370bc7a7f4296cfb9`.
It contains Iris's previous firmware and persistent flash data. Her SD card
was not changed. The image was restored on the same date and its flash hash
was verified by `esptool`.

To restore the exact pre-test state, connect the CH340/UART port to Nexus and
run:

```sh
/noobia/iris/.arduino-cli/data/packages/esp32/tools/esptool_py/5.3.1/esptool \
  --port /dev/ttyUSB0 --baud 460800 write-flash 0x0 \
  /noobia/iris/backups/iris-before-wifi-dongle-2026-09-28.bin
```

For the retired experiment, the NanoPi's `/usr/local/sbin/iris-wifi-connect` sends the `sta` command over
the USB CDC port; it reads root-only `/etc/iris-wifi.conf`. The source for that
helper is in [`../../neo/iris-wifi-connect.sh`](../../neo/iris-wifi-connect.sh).
The credentials are **not** compiled into Iris's firmware. USB enumeration,
Wi-Fi association, DHCP, and routing still need to be tested after Iris is
connected to the NanoPi's USB host port. It does not configure the restored
Noob firmware or the planned combined firmware.
