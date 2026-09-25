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

- OV2640 camera and one-bit SD_MMC storage.
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

The installed workspace build can be run with:

```sh
./iris/tools/build_iris.sh --build-dir ./build/iris
```

Production builds should also select 16 MB flash, the huge-app partition,
QSPI PSRAM, and QIO flash mode as documented for the installed board.

Device-local build trees, flash backups, photographs, bridge logs, and compiled
host utilities are intentionally not stored here.
