# Iris

Iris is the first ESP32-S3 implementation of the common Noob embedded runtime.
The design keeps portable execution machinery separate from physical-board
knowledge:

- `runtime/` — transports, NRP/1 protocol, command dispatcher, VM, native
  registry, and reusable ESP32 services.
- `firmware/iris_noob/` — the Iris composition root, capability registration,
  and all verified Iris pin assignments.
- `programs/` — named, wire-ready Noob VM bytecode programs.
- `tools/` — native C and shell tools used by Nexus over UART and BLE.

## Verified Iris hardware

- OV2640 camera and one-bit SD_MMC storage.
- MSM261D3526H1CPM microphone: data GPIO35, clock GPIO36, word-select GPIO37.
- SK6812 RGB LED on GPIO33.
- Green signal LED on GPIO34.
- Native USB GPIO19/20 and USB-UART GPIO43/44.

See [`firmware/iris_noob/README.md`](firmware/iris_noob/README.md) for firmware operation and
[`programs/README.md`](programs/README.md) for VM program controls.

From the repository root, compile with Arduino CLI using `iris/` as an
additional library search directory:

```sh
arduino-cli compile --fqbn esp32:esp32:esp32s3 \
  --libraries iris iris/firmware/iris_noob
```

Production builds should also select 16 MB flash, the huge-app partition,
QSPI PSRAM, and QIO flash mode as documented for the installed board.

Device-local build trees, flash backups, photographs, bridge logs, and compiled
host utilities are intentionally not stored here.
