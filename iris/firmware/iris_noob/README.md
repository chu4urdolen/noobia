# Iris on NoobRuntime

Iris is the first physical Noob using the common runtime. Her implementation is
under `src/noobs/iris` and contains all verified pin assignments, hardware
initialization, capability registration, and native functions.

The sketch only creates the runtime, attaches a stream transport, asks Iris to
register herself, and services the runtime loop.

BLE is the preferred transport. The Nexus controller identity lives in
`src/noobs/iris/nexus_peer_config.h`, outside the reusable transport. Iris scans
for five seconds at boot and then no more than once every thirty seconds while
disconnected. UART remains enabled as a recovery transport.

Registered native functions:

- `100 CAMERA_CAPTURE`: capture an SVGA JPEG to the next sequential path in
  `/captured`; returns the sequence number.
- `101 STORAGE_STATUS`: return SD capacity and usage.

The current runtime also exposes generic path-based SD deletion/listing,
Wi-Fi connection and credential updates, BLE discovery/peer updates, I2C,
WAV recording, raw MJPEG recording, and persistent named VM programs. Run
`CAPS` for the authoritative IDs and names compiled into a device.

GPIO diagnostics live separately in `esp32_common/NoobEsp32Diagnostics`.
Iris only supplies that library with her reserved-pin map and the explicit
allowlist for pull-only tests.

Before compiling a local image, set `WIFI_PASSWORD` in `iris_secrets.h`.
Credentials changed through `WIFI_CREDENTIALS_SET` are persisted in NVS.
- `120 MIC_LEVEL`: return the current microphone RMS level.
- `121 MIC_ABOVE`: compare microphone level with a VM-provided threshold.
- `130 LED_RGB`: set the onboard SK6812 RGB pixel.
- `131 LED_SIGNAL`: control the separate green signal LED.

Verified capabilities are reported through `CAPS`. Capabilities describe
hardware availability; a native function is callable only when it is also
listed in the function registry.
