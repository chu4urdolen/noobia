# NoobRuntime

NoobRuntime is the common embedded execution environment for physical Noobs.
It contains no board names, pin assignments, or Iris-specific branches.

This library lives at `esp/common` because it is shared infrastructure. A
physical Noob directory contains only composition, pin assignments, local
capabilities, and hardware-specific policy.

## Runtime path

    transport -> NRP/1 parser -> command dispatcher
              -> VM or native registry -> NRP/1 reply -> transport

Current modules:

- `src/transport`: interchangeable transport interface, an Arduino `Stream`
  implementation for UART/USB, and an outbound BLE client transport.
- `src/protocol`: versioned request/reply framing and parse errors.
- `src/commands`: common command dispatcher.
- `src/vm`: bounded bytecode VM.
- `src/syscalls`: numeric/name native-function registry.
- `src/core`: runtime orchestration and capability registry.
- `src/services`: reusable native implementations. Board composition supplies
  hardware configuration; services contain no Iris pin assignments.
- `src/hal`: reusable HAL contracts. Concrete ESP32 HAL implementations will
  be added as capabilities require them.

## Functions and programs

`NoobFunction` is the single callable interface. BLE `CALL`, VM `SYS`,
threads, and sequences all resolve an ID through `NativeRegistry` and invoke
the same object. Existing callback-based services are wrapped by adapters, so
services can migrate to classes independently.

`NoobProgram` adds a program type:

- `NoobThreadProgram` runs a cooperative step continuously until its stopper
  function is called.
- `NoobSequenceProgram` owns one to four channel definitions and starts the
  common timed sequencer. Each channel has its own interval and bit array.

Every channel has a bounded 16-integer result queue and a `channel_busy` bit.
The wrapper sets busy before the channel body and clears it on every return.
When the queue is full, the oldest value is replaced and the drop counter is
reported. No program can consume unbounded RAM.

## Common native ABI

IDs 1–99 are reserved for functions supplied by `NoobRuntime` itself. Physical
Noobs use IDs from 100 upward for registered hardware functions.

- `1 TIME_NOW`: no arguments; returns the raw 32-bit monotonic millisecond
  counter and reports the unsigned value in reply details.
- `2 TIME_RESET`: no arguments; sets the logical monotonic epoch to the current
  hardware counter, making the next `TIME_NOW` value begin near zero.
- `3 SEQUENCE_SET`: configure a channel. Text form is
  `slot interval_ms function bits [fixed_args...]`. VM form is
  `slot interval_ms function_id bit_count packed_bits [fixed_args...]`.
- `4..7`: `SEQUENCE_START`, `SEQUENCE_STOP`, `SEQUENCE_STATUS`, and
  `SEQUENCE_CLEAR`.
- `8..11`: `SEQUENCE_POP`, `SEQUENCE_QUEUE_SIZE`,
  `SEQUENCE_QUEUE_CLEAR`, and `SEQUENCE_BUSY`.

Both functions are registered by the common runtime and therefore do not appear
in Iris-specific composition code. This is monotonic timing, not civil time;
the logical epoch is not retained across reboot because boot already starts it
at zero.

Portable bytecode examples live in `programs/`. Programs that call a physical
Noob's IDs remain in that Noob's own program directory.

The BLE transport seeks a configured peer GATT server, subscribes to command
notifications, writes replies, and reconnects on a bounded schedule. Automatic
scanning is nonblocking. GATT connection stays in the BLE library's supported
task context and may briefly pause the cooperative runtime; failed attempts are
rate-limited. Future Wi-Fi transports should implement the same
`NoobTransport` contract; neither transport needs to alter the protocol,
dispatcher, or VM.
