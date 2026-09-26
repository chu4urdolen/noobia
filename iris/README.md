# Iris

Iris is the first ESP32-S3 implementation of the common Noob embedded runtime.
The design keeps portable execution machinery separate from physical-board
knowledge:

- `../esp/common/` — transports, NRP/1 protocol, command dispatcher, VM,
  native registry, reusable ESP32 services, and portable VM examples.
- `firmware/iris_noob/` — the Iris composition root, capability registration,
  and all verified Iris pin assignments.
- `programs/` — named, wire-ready Noob VM bytecode programs.
- `tools/` — native C and shell tools used by Nexus over UART and BLE.
- `diagnostics/` — configurable source tests and historical hardware probes.

## Verified Iris hardware

- OV2640 camera and SD-card storage over SPI (CLK 42, CMD/MOSI 39,
  DAT0/MISO 41, DAT3/CS 38). The former one-bit SDMMC path corrupted raw IR
  captures on this board; see `diagnostics/SD_IR_CAPTURE_20260926.md`.
- MSM261D3526H1CPM microphone: data GPIO35, clock GPIO36, word-select GPIO37.
- SK6812 RGB LED on GPIO33.
- Green signal LED on GPIO34.
- Native USB GPIO19/20 and USB-UART GPIO43/44.
- Current attachments: photoresistor GPIO1, DHT11 GPIO15, ultrasonic trigger
  GPIO16/echo GPIO48, blue LED GPIO17, IR receiver GPIO18/transmitter GPIO40,
  and red LED GPIO47.

Pins and electrical assignments live only in `iris_config.h`; reusable runtime
services receive configuration and contain no Iris pin knowledge.

The common thread, sequence, queue, and `channel_busy` flow is documented in
[`../esp/common/PROGRAM_MODEL.md`](../esp/common/PROGRAM_MODEL.md).

See [`firmware/iris_noob/README.md`](firmware/iris_noob/README.md) for firmware operation and
[`programs/README.md`](programs/README.md) for VM program controls.

Host defaults live in `tools/iris-tools.conf`; `irisctl --help` lists path and
device overrides. Firmware build defaults live in `tools/iris-build.conf`.
Copy `iris_secrets.local.h.example` to `iris_secrets.local.h` for local Wi-Fi
provisioning. The local file is ignored and must never be committed.

Common syscall ID `1` is `TIME_NOW`, a monotonic 32-bit millisecond counter
registered by `NoobRuntime` for every Noob. `irisctl time-now` calls it directly;
`../esp/common/programs/time_now.hex` demonstrates calling it from VM bytecode.
Common syscall ID `2` is `TIME_RESET`; `irisctl time-reset` establishes a new
logical zero without resetting Iris or disturbing hardware timers.

Iris-specific behavior is split further:

- `hw_*`: elementary Iris hardware bindings and SD artifact writers.
  and ultrasonic distance.
- `seq_*`: finite/repeating LED, camera, and IR programs.
- `thread_*`: continuous detector and sampling programs with queues.
- `vm_*`: VM assembly listings and wire-ready bytecode.
- `noob_*`: reusable common runtime architecture under `esp/common`.

`BLUE_BLINK_SEQUENCE` and `POLICE_SEQUENCE` are callable from BLE or VM.
`ULTRASONIC_CHANGE_START` and `LIGHT_CHANGE_START` establish live sensor
baselines, then queue timestamps only when their configured dynamic delta is
crossed. Neither relies on an absolute environmental value.
`MIC_RISE_START` stores ten one-second loudness integers, never raw audio. It
compares the older five-second mean with the newer five-second mean.

## IR button recordings

`irisctl ir-scan-start 300000` listens for remote presses. Each captured
receiver transition and its duration in microseconds is kept in RAM and written
to `/samples/ir_raw_<time_ms>.csv`. `irisctl ir-scan-pop` gives the timestamp.
The writer reads the whole file back and checks its size and checksum before
the capture is reported as saved. If the SD card fails verification, the last
waveform remains available in RAM until Iris restarts or another capture arrives.

`irisctl ir-replay-last` transmits the latest RAM waveform and stops the scan.
`irisctl ir-verify-last` also records that transmission through Iris's IR
receiver and reports pulse count and timing differences against the original.
`irisctl ir-replay <time_ms>` loads and validates a saved waveform before
transmitting it. After popping a saved capture, `irisctl ir-remember ThomsonTV
Power` adds its timestamp to `/noob/ir_dictionary.csv` for labeling. The IR
receiver removes the carrier; replay regenerates it at Iris's configured
38 kHz while preserving the observed pulse durations.
Local transmitter/receiver loopback worked, but the saved Thomson TV Mute
recording did not control the TV in the 2026-09-26 test. Treat remote replay
as experimental until the optical path and waveform are independently checked.

The installed workspace build can be run with:

```sh
./iris/tools/build_iris.sh --build-dir ./build/iris
```

Production builds should also select 16 MB flash, the huge-app partition,
QSPI PSRAM, and QIO flash mode as documented for the installed board.

Device-local build trees, flash backups, photographs, bridge logs, and compiled
host utilities are intentionally not stored here.
