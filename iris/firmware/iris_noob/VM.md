# Noob VM version 1

The VM has 1,024 bytes of program storage, 256 bytes of data memory, eight
signed 32-bit registers, and an eight-entry return stack. All multi-byte values
are little-endian. Execution is cooperative and bounded per runtime loop.

| Opcode | Encoding | Operation |
|---|---|---|
| `00` | `00` | halt |
| `01` | `01 dst imm32` | move immediate |
| `02` | `02 dst src` | move register |
| `03` | `03 dst a b` | add |
| `04` | `04 dst a b` | subtract |
| `05` | `05 dst a b` | multiply |
| `06` | `06 dst a b` | divide |
| `10` | `10 addr16` | jump |
| `11` | `11 reg addr16` | jump if zero |
| `12` | `12 reg addr16` | jump if nonzero |
| `13` | `13 addr16` | call VM subroutine |
| `14` | `14` | return |
| `20` | `20 dst func16 argc regs...` | native syscall |
| `21` | `21 milliseconds16` | nonblocking wait |
| `30` | `30 dst address8` | load memory byte |
| `31` | `31 address8 src` | store memory byte |

Verified programs:

- Waiting loop with `r0=42`: `01002a00000021e803100600`
- Compute `7+5` into `r2`: `0100070000000101050000000302000100`
- Iris camera syscall 100: `200064000000`
- Common `TIME_NOW` syscall 1 into r0: `200001000000`
- Common `TIME_RESET` syscall 2: `200002000000`

## Threads and sequences

`RUN` and `START_THREAD` start the loaded VM program. A looping program is a
cooperative thread; `STOP` and `STOP_THREAD` interrupt it, and
`THREAD_STATUS` inspects it.

Syscall 3 configures a sequencer channel from registers:

    slot, interval_ms, function_id, bit_count, packed_bits, [fixed_args...]

The most significant selected bit runs first. For example, decimal 682 with a
bit count of 10 is `1010101010`. Syscall 4 starts all configured channels;
argument 0 means finite and 1 means repeat. Syscalls 8–11 pop queued integer
results, read queue size, clear a queue, and inspect `channel_busy`.

`police_sequence_vm.hex` proves the runtime path by defining Iris's blue and
red channels entirely from VM registers and then halting while the common
sequencer completes the physical work.

`police_on_ultrasonic_change.hex` starts the compiled 250 ms ultrasonic
thread, polls function 206 for detection timestamps, and calls the compiled
police sequence (function 201) whenever a meaningful change arrives. It waits
for common `SEQUENCE_STATUS` to become idle before accepting another event.
The corresponding `.asm` file is a readable annotated listing.

`light_change_start.hex` calls Iris function 207 with a dynamic-delta margin
of 200 ADC counts and a 250 ms interval. Function 211 is its nonblocking event
poll; each nonzero result is the logical time at which light changed.

`police_on_sensor_change.hex` combines ultrasonic and photoresistor events.
The light thread stays running while police executes, but sampling is suppressed
by sequence `channel_busy` bits 0 and 1 for their complete execution lifetime.
The thread takes a fresh light baseline when both LED channels finish.

`mic_rise_start.hex` starts functions 212--216 with a 200% rise ratio and
minimum RMS 20. `police_on_loudness_rise.hex` polls its timestamp queue and
runs the same finite police sequence. Raw sound is reduced immediately into one
integer per second; only ten integers remain in the rolling frame.
`police_on_any_change.hex` starts all three native detector threads. Any
ultrasonic, light, or microphone timestamp starts the finite police sequence.
Light sampling pauses on LED busy, microphone repeats use its rearm gate, and
ultrasonic events accumulated during the sequence are drained.
Common native IDs occupy 1–99 and are registered by `NoobRuntime`. Physical
Noob functions begin at 100. `TIME_NOW` returns monotonic milliseconds as the
raw 32-bit value in the signed VM register; arithmetic should treat wraparound
normally rather than interpreting the sign as wall-clock time.

Portable programs live in `/noobia/esp/common/programs`; Iris-specific programs
live in `/noobia/iris/programs`. Together they contain wire-ready examples for
time, arithmetic, one-shot capture, timed RSSI gathering, and sound-triggered
capture.

Native failures and invalid bytecode place the VM in `FAULT`. `RESET_VM` clears
program memory, data memory, registers, call stack, and fault state.
