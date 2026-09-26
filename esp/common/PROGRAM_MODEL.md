# Noob threads and sequences

This is the common behavior model shared by physical Noobs. Hardware remains
native compiled code; the VM combines those native functions at runtime.

## Call path

    BLE/UART command or VM SYS
        -> NativeRegistry
        -> NoobFunction
        -> native hardware service or NoobProgram

`NoobFunction` is the common callable interface. A board registers concrete
objects with numeric IDs and names. The VM knows IDs, not GPIOs or board names.

`NoobProgram` adds a type to a callable function:

- `NoobSequenceProgram` starts finite or repeating timed channel patterns.
- `NoobThreadProgram` runs one cooperative step at a fixed interval until
  stopped.

Both are native objects, so BLE `CALL` and VM `SYS` invoke the same code.

## Channels

`NoobProgramChannel` binds:

- one registered native function ID;
- zero to seven fixed integer arguments;
- one dynamic integer input;
- a bounded queue of returned records;
- status and error details;
- a `busy` bit.

Invocation is always `void` from the scheduler point of view. Before the
native body is called, the wrapper sets `busy=1`. It queues a successful
record when useful, then sets `busy=0`. Missing functions and failed calls also
clear the bit before returning.

A record holds up to six `(name, integer)` fields. A queue slot can therefore
represent one coherent observation such as `{time_ms, protocol, address,
data, repeat}`. Existing scalar functions are automatically wrapped as
`{value:n}`. Queues hold eight records; when full, the oldest record is
discarded and a drop counter is incremented. Both dimensions are fixed, so RAM
use remains bounded.

BLE/UART `POP` replies serialize the complete record. A VM receives its primary
field in the syscall destination register for backward compatibility, then can
read other fields by index with the corresponding `*_FIELD` function. Field
names travel in command diagnostics; VM bytecode remains integer-only.

## Sequence arrays

A sequence owns one to four `ChannelDefinition` entries. Each definition has:

    function_id, interval_ms, bits[], fixed_arguments[]

At each channel interval, its current bit becomes the dynamic input to the
native function. An LED channel therefore receives `1` or `0`. Channels
have independent positions, queues, and `channel_busy[slot]` bits.

The common sequencer arrays are:

- `tracks[4]`: channel definitions and current positions;
- `channelBusy[4]`: whether each channel is executing its sequence.

`SEQUENCE_STATUS` reports all busy bits and positions. `SEQUENCE_BUSY slot`
returns one bit directly. A finite sequence stops after every active track
reaches its final bit. Only one common sequence owns the sequencer at a time;
starting a compiled sequence replaces the previous definition.

`channel_busy[slot]` is set when a sequence starts and remains set until that
channel reaches its end. Stop and error paths clear every bit. The low-level
`NoobProgramChannel::busy` flag remains separate and covers one native call.

VMs may call a compiled sequence, or build one through `SEQUENCE_SET`.

## Thread arrays

A thread has one logical output channel:

- `channelBusy_[1]`: set when the thread starts and cleared when it stops;
- one eight-record event queue;
- one interval and next-run time;
- running state.

Derived classes implement `step()` and call either `publish(value)` or
`publish(record)` only when an event should become visible. `POP` treats an
empty queue as an error, which
is useful for interactive diagnostics. `POLL` is intended for VM loops: it
returns zero when empty and the next event value otherwise.

`NoobChangeThreadProgram` is a reusable derived thread. Its first reading
becomes the runtime baseline; it compares later readings with the preceding
reading and never assumes an absolute sensor value. The physical Noob supplies
the native source function, sensitivity delta, interval, and rearm sample count.

`NoobWindowRiseThreadProgram` is another reusable derived thread. It reduces
frequent integer samples into ten fixed-duration buckets and stores no raw
samples. Each update compares the five oldest bucket means with the five newest.
A configurable ratio and minimum level produce one timestamp event, followed by
a configurable number of false comparisons before rearming.
The runtime calls all thread and sequence services cooperatively. No background
service blocks the command transports or owns an unbounded task.

## VM lifecycle persistence

`NoobRuntime::setVmLifecycle()` installs an optional lifecycle observer.
Successful `RUN`/`START_THREAD`, explicit `STOP`/`STOP_THREAD`, and
`RESET_VM` notify it. The ESP32 SD program store uses this to keep a
recoverable runtime snapshot without coupling the dispatcher to SD or Iris.

A started VM is restored and run after boot. An explicitly stopped VM is
restored in the ready state, while reset clears the boot selection. Temporary
and backup files protect the previous snapshot if an SD write is interrupted.

## Iris examples

Iris registers low-level functions in `hw_functions.cpp`, compiled LED
sequences in `seq_leds.cpp`, and continuous detector instances in
`thread_detectors.cpp`.

The IR learner records each demodulated receiver edge to `/samples/` and
publishes structured channel records. Known NEC and RC5 frames expose
`address` and `data`; the observed Thomson-TV signal is preserved as a 24-bit
pulse-distance `code` because the captured waveform does not justify splitting
it into address and command fields. Learned button labels are appended to
`/noob/ir_dictionary.csv` with protocol, available fields, and capture time.

The police sequence has two 200 ms channels:

    blue: 10101010100
    red:  01010101010

The first ten states are alternating flashes. The explicit final zero at two
seconds leaves both LEDs off.

The ultrasonic thread samples every 250 ms. It compares the current distance
with the immediately preceding distance. A change of at least 100 mm publishes
the logical monotonic detection time, not the distance. It then disarms until
four consecutive readings are stable within one quarter of the threshold. This
turns continuous motion into one event episode instead of a timestamp flood.

The photoresistor thread uses the same common class. It establishes its
baseline from the current room light, samples every 250 ms, and by default
requires a 200-count ADC delta. BLE or VM callers may supply a different delta.
Events contain logical monotonic timestamps. Iris skips light samples while
police LED channels 0 or 1 are busy, then takes a fresh post-sequence baseline.

`vm_police_on_ultrasonic_change.hex` composes both native classes:

1. Start the ultrasonic thread with a 100 mm delta and 250 ms interval.
2. Poll its timestamp queue.
3. When a timestamp appears, call the compiled police sequence.
4. Wait for that sequence to finish.
5. Drain events accumulated while the LEDs were busy, then resume polling.

The readable bytecode listing is stored beside the wire-ready hex file.

## Adding another behavior

1. Implement or reuse a `NoobFunction` for each physical action.
2. Register it in the physical Noob composition root.
3. Derive a sequence or thread class only for reusable native policy.
4. Publish a named record when an event has several values; use a scalar
   timestamp when only occurrence matters.
5. Compose registered functions from VM bytecode for replaceable high-level
   logic.

Pin numbers and board wiring never enter the VM or common program classes.
