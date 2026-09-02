# Noob VM program store

This directory is the local, inspectable store for portable Noob VM programs.
Each `.hex` file contains VM version-1 bytecode in wire-ready hexadecimal.
Programs call capabilities by registered function ID; physical pin assignments
remain in each Noob-specific module.

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

- `arithmetic`: computes 7 + 5 into register 2 and halts.
- `camera_once`: captures one photograph and halts; register 0 receives its
  sequence number.
- `rssi_ten_seconds`: starts the native RSSI event service for ten seconds,
  stops it, and halts.
- `sound_capture`: continuously listens for a loud sound and takes a photo.
- `sound_capture_test`: same control flow with threshold 1, intended only for
  deterministic integration testing.
- `led_blink`: softly blinks the onboard addressable status LED.
