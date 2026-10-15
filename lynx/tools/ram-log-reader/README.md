# Lynx fixed-region RAM reader: offline component

The two callbacks return a diagnostic marker or the exact pstore RAM region
0x48090000..0x48170000 (0xe0000 bytes), confirmed by saved Lynx bootloader logs.
They do not accept address/length input, touch storage APIs, change security
policy, or provide arbitrary writes/calls. The marker identifies this diagnostic
reader, not native Linux startup. Do not confuse it with the native PID1 marker.

`build.py` uses the workspace-only cross compiler and produces the ARM64 callback
object plus a separate Linux test executable. `emulate_test.py` runs that test
executable under the exact stock kernel in QEMU with fake channel callbacks and
synthetic RAM. Host and ARM tests passed: 224 packets transfer every pstore byte,
supplied address input is ignored, and 13 rejection/abort cases stop correctly.
Evidence is in `build-report.json` and `arm-emulation/result.json`.

This is **not a deployable download-agent payload**. No DA entry, command
registration, heap repair, exploit transport or live callback ABI has been proven.
The ARM tests run on Linux, not inside a physical MediaTek loader. None of these
components has been sent to Lynx. A RAM-loader transition may alter the crash
record even if a future reader succeeds. Preserve every raw dump and its hashes.

The separate `../mtk_aio_readiness.py` is an earlier, smaller hardware prerequisite
probe. It uses the exact previously accepted stock DA1/DA2, checks MT6983
preloader mode, and requests a short benign filename through the loader's
all-in-one-signature interface. It stops before uploading signature/payload data.
It exposes no storage reads/writes, authentication bypass, heap corruption or
general-purpose command execution. Default invocation is offline plan;
`--self-test` uses mocks; `--connect` is bounded to three minutes waiting and
two minutes after handshake, with no automatic fallback. A returned download
request proves command availability only. The loader may await a file afterwards;
power cycle to discard that RAM session and reestablish Fastboot.

Compiler packages were downloaded/extracted under `../aarch64-gcc`, without
system installation. Package hashes and compiler hashes are preserved there.
The reader uses the tiny ARM64 code model for its eventual runtime relocation;
the actual loader integration still requires an independently verified entry.
