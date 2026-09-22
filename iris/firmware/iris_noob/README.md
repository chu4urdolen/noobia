# Iris on NoobRuntime

Current attachments: photoresistor GPIO1, DHT11 GPIO15, ultrasonic trigger
GPIO16/echo GPIO48, blue LED GPIO17, IR receiver GPIO18/transmitter GPIO40,
and red LED GPIO47. External I2C/OLED is disabled in this profile because its
former GPIO17/18 pair is occupied. Historical OLED probes remain under
`diagnostics/` and take their pins from `diagnostic_config.h`.

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

The current profile includes these native services:

- `100 CAMERA_CAPTURE`: capture an SVGA JPEG to the next sequential path in
  `/captured`; returns the sequence number.
- `101 STORAGE_STATUS`: return SD capacity and usage.
- SD listing, chunk reading, general file deletion, and VM program storage.
- Microphone level/threshold and WAV recording; camera MJPEG recording.
- Wi-Fi connect/disconnect, credentials, scan, RSSI gathering and events.
- BLE scanning, peer configuration/status, and onboard LED controls.
- DHT11, ADC/light, IR carrier/read/loopback, ultrasonic ranging, and external
  digital LEDs. VM bytecode invokes these by native function ID.

`CAPS` reports compiled capabilities and registered function names/IDs. Check
native results for hardware readiness; registration alone does not prove it.

## Restored build

Run `tools/build_iris.sh --build-dir DIR`. It selects 16 MB flash, QSPI PSRAM,
and a 3 MB application partition. Its symbol checks require hardware I2C and
reject the SH1107/U8g2 and software-I2C diagnostic code. Camera-internal SCCB
remains necessary for the camera.

Hardware selection and tuning stay in `src/noobs/iris/iris_config.h`; reusable
native implementations stay in `NoobRuntime`. Real provisioning credentials go
in ignored `iris_secrets.local.h`, copied from the tracked example.

Remote controls include `irisctl dht-read`, `light-read`, `ir-test`,
`ultrasonic-read`, and `external-led`. Use `irisctl --help` for the full set.

Live test sources are in `diagnostics/`; generated results remain local.
