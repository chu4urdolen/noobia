# All-detector VM live test — 2026-09-23

Program: `police_on_any_change.hex`

- BLE load: `loaded=107`
- VM: `WAITING`, 107 bytes
- Ultrasonic thread: running, 250 ms, queue empty, no drops
- Light thread: running, 250 ms, queue empty, no drops
- Microphone thread: running, 100 ms chunks, 10/10 one-second buckets,
  200% ratio, minimum RMS 20, no drops
- SD copy: `/programs/police_on_any_change.nvm`, 107 bytes

The first 125-byte draft exceeded the current single BLE-notification frame and
arrived with one hex nibble missing. The final program removes redundant light
and microphone drain loops and fits in 107 bytes. It then loaded and started
entirely over BLE. Light sampling already pauses during LED activity, microphone
events already have a rearm gate, and the VM drains ultrasonic events collected
during a police sequence.
