# Universal native channel calls

Common code owns argument handling; pin assignments stay in the Iris module.
`NoobProgramChannel` carries fixed integers and a copied printable ASCII string
(maximum 255 bytes). Every invocation resolves the native registry and calls
`callMixed`. Empty text preserves ordinary numeric calls. Result records enter
the channel queue; busy is cleared on success, missing function and error.

## Configure from VM or BLE

The new mixed form of SEQUENCE_SET is:

```text
CALL_MIXED SEQUENCE_SET slot interval_ms function_id bit_count packed_bits append_bit [fixed_args...] "ASCII"
```

`append_bit=1` preserves LED-style calls: append the current 0/1 pattern bit.
`append_bit=0` sends only fixed arguments and ASCII. This permits no-argument,
text-only and mixed functions without injecting an unwanted integer. Each
pattern position invokes the function, including zero positions; bits are data,
not a universal skip/execute mask. Numeric/text legacy SEQUENCE_SET forms retain
their existing behavior. The VM uses SYS_MIXED with the same argument order.

Example: one OLED draw through Neo, with the filename as ASCII (function 273):

```text
CALL_MIXED SEQUENCE_SET 0 250 273 1 1 0 "Iris_formatted.gif"
CALL SEQUENCE_START 0
```

Transport/VM mixed frames allow at most eight integers, so this form has room
for two fixed target arguments after its six scheduling fields. Compiled channel
definitions allow seven fixed arguments. Target functions still enforce their
own argument counts and hardware availability; no dispatcher bypass is added.

## Compiled sequence/thread classes

`SequenceService::ChannelDefinition` adds `ascii` and `appendInput`, defaulting
to `""` and true so existing LED classes behave unchanged. New definitions may
bind any registered native function with its proper arguments.

`NoobSamplingThreadProgram` accepts source ASCII in its constructor, or via
`callMixed([duration_ms, interval_ms], ASCII)` when starting it. It invokes the
source without a pattern bit and queues its structured result. Custom thread
classes can use the same `NoobProgramChannel` directly.

Protocol controls (LOAD/RUN/STOP/RESET_VM) are not native channel functions.
Disabled GPIO diagnostics remain unavailable; peer calls require Neo online.
Do not schedule destructive functions or credential changes automatically.

Tests: `bash esp/common/tests/run-channel-calls.sh` exercises mixed/text calls,
sequence definitions, sampling threads, result queues and error busy cleanup.
Deployment (2026-10-04): firmware flashed with verified hashes. The live
`diagnostics/vm_sequence_sd_read.hex` test passed via SYS_MIXED -> sequence ->
SD_READ -> channel queue, returning 30 bytes and halting normally. Police-on-all
was restored with startup autorun. Text-only and sampling-thread paths passed
host tests. With native USB reconnected, an ASCII sequence targeting
NEO_OLED_TEXT (274) successfully sent "Iris channel OK" to Neo. Sequence busy
bits cleared, its queue returned value=1, and Neo's draw worker exited 0.
Police-on-all and startup autorun were restored after the test.
