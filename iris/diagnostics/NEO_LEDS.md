# Neo LED VM test

`vm_neo_led_sequence.hex` is a bounded hardware diagnostic.
It clears generic sequence slots, configures slot 0 for Neo physical pin 23
(native 275), emits 1010101010 at 100ms steps, waits 4000ms, then records the
queue length in r2 and halts. Expected r2=8 (queue capacity), two oldest results
dropped, sequence stopped, pin 23 LOW. Packed bits are MSB-first: decimal 682.
RUN temporarily updates the last-program autorun snapshot; always restore
police_on_all afterward. The named saved police VM is not overwritten.

Before testing, stop the current VM. Load this file with irisctl's --programs
pointing here, RUN, then inspect STATUS, SEQUENCE_STATUS and NEO_LED_STATUS 23.
Afterward STOP, load saved police_on_all, RUN. Native 275 must be present in
live CAPS and the ESP native USB must be connected to Neo.

Verified 2026-10-05 over BLE: HALTED pc=76, r2=8, positions=10/10,
running=0, all sequence busy flags zero, queue dropped=2, pin 23 value=0.
Restored police_on_all (138 bytes), WAITING pc=135, persisted autorun=1.
