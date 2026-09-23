# Noob VM program store

This directory stores Iris-oriented VM programs. Hardware-independent examples
live in `../../esp/common/programs`. Each `.hex` file contains VM version-1
bytecode in wire-ready hexadecimal. Programs call capabilities by registered
function ID; physical pin assignments remain in each Noob-specific module.

Use the Nexus controller:

```text
irisctl programs
irisctl vm-load sound_capture
irisctl vm-run
irisctl vm-status
irisctl vm-stop
```

`sound_capture` measures a short audio window four times per second. At or above
50 RMS counts it captures a JPEG to `/captured/`, waits three seconds, and then
resumes listening. Adjust its first immediate (`32 00 00 00`, decimal 50) after
observing the installed enclosure noise floor.

## Included programs

- `camera_once`: captures one photograph and halts; register 0 receives its
  sequence number.
- `rssi_ten_seconds`: starts the native RSSI event service for ten seconds,
  stops it, and halts.
- `sound_capture`: continuously listens for a loud sound and takes a photo.
- `sound_capture_test`: same control flow with threshold 1, intended only for
  deterministic integration testing.
- `led_blink`: softly blinks the onboard addressable status LED.
- `police_lights`: alternates Iris's blue and red external LEDs every 125 ms,
  producing four complete blue/red cycles per second until the VM is stopped.
- `police_sequence_vm`: defines two 200 ms sequencer channels from VM
  registers, using packed patterns `10101010100` and `01010101010`, starts
  ten alternating flashes in two seconds, and halts while the common sequencer
  finishes it with both LEDs off.
- `ultrasonic_change_start`: starts Iris's ultrasonic change-detection
  thread with a 100 mm threshold and a 250 ms sampling interval. Events contain
  logical detection times, not distance values.
- `police_on_ultrasonic_change`: continuously polls those timestamp events
  and starts the compiled police sequence after each detected change. Events
  accumulated during a light burst are coalesced instead of replayed. The
  adjacent `.asm` file documents every bytecode instruction.
- `storage_mic`: SD capacity in r0, microphone RMS in r1, then halt.
- `audio_one_second`: record a one-second WAV to SD; sample count in r1.
- `video_one_second`: save two JPEG frames as a one-second MJPEG; count in r2.
- `radio_status`: Wi-Fi status in r0 and BLE connection state in r1.

Run `diagnostics/restore_smoke.nrp` with `tools/noobctl_batch` to test native
calls and following PINGs over the same UART connection.
