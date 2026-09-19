# Iris on NoobRuntime

Current wiring (2026-09-19, firmware `0.2.8-i2c-17-18`): OLED SDA=GPIO17,
SCL=GPIO18; LEDs remain on GPIO15 (channel 0) and GPIO40 (channel 2).
Removed LED channels 1/3 are rejected; LED calls no longer alter I2C.
I2C stays dormant until `I2C_CONFIG [frequency]`. `I2C_SCAN [first [last]]`
accepts decimal addresses 8..119 and reports ACK/NACK/timeout/other counts.
Use `CALL I2C_SCAN 60 61` for OLED addresses 0x3C/0x3D.
The address-only BLE test is `diagnostics/oled_17_18_ble.sh`.
ESP-IDF 5.5.5 runs these address probes at a fixed 100 kHz, even when
`I2C_CONFIG` selects a different speed for data writes. The separate
`diagnostics/oled_17_18_slow_command_ble.sh` tests a 10 kHz display-off write.
See `diagnostics/OLED_20260919.md` for the measured results and limitations.

Iris is the first physical Noob using the common runtime. Her implementation is
under `src/noobs/iris` and contains all verified pin assignments, hardware
initialization, capability registration, and native functions.

The sketch only creates the runtime, attaches a stream transport, asks Iris to
register herself, and services the runtime loop.

BLE is the preferred transport when `nexus_peer_config.h` contains a real
Nexus controller MAC. Iris scans for five seconds at boot and then no more than
once every thirty seconds while disconnected. UART remains enabled as a recovery
transport. The configured Nexus peer is `00:E0:4C:23:99:87`; its GATT bridge
must be running to accept Iris's connection.

The current lazy-I2C profile includes these native services:

- `100 CAMERA_CAPTURE`: capture an SVGA JPEG to the next sequential path in
  `/captured`; returns the sequence number.
- `101 STORAGE_STATUS`: return SD capacity and usage.
- SD listing, chunk reading, general file deletion, and VM program storage.
- Microphone level/threshold and WAV recording; camera MJPEG recording.
- Wi-Fi connect/disconnect, credentials, scan, RSSI gathering and events.
- BLE scanning, peer configuration/status, and onboard LED controls.
- Hardware I2C on Iris GPIO17/18: lazy start, scan, short read/write,
  register-read and explicit close. No bus operation occurs during boot.

`CAPS` reports compiled capabilities and registered function names/IDs. Check
native results for hardware readiness; registration alone does not prove it.

## Restored build

Run `bash /noobia/iris/tools/build_iris.sh`. It selects 16 MB flash, QSPI PSRAM,
and a 3 MB application partition. Its symbol checks require hardware I2C and
reject the SH1107/U8g2 and software-I2C diagnostic code. Camera-internal SCCB
remains necessary for the camera.

Hardware selection stays in `src/noobs/iris/iris_config.h`; reusable native
implementations stay in `libraries/NoobRuntime`. External hardware I2C is
compiled but dormant until `I2C_CONFIG`; OLED, bit-bang I2C and broad GPIO
diagnostics are not enabled.

Remote controls: `irisctl i2c-lines`, `irisctl i2c-start [HZ]`,
`irisctl i2c-scan`, and `irisctl i2c-close`. `I2C_LINES` reads SDA/SCL without
changing pin modes or starting the controller. The generic `I2C_WRITE`,
`I2C_READ`, and `I2C_WRITE_READ`
natives are available to commands and VM programs after start. Iris constrains
configuration to her board pins; callers may select only 10–400 kHz.

Live test scripts and results are in `/noobia/iris/diagnostics/`. See
`RESTORATION_20260915.md` there for verified behavior and remaining limitations.
