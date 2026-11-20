# Neo LED channels

Ten physical 24-pin header pins are independently addressable:
7, 11, 12, 13, 15, 19, 21, 22, 23, 24. Each LED needs its own resistor.
Wiring is isolated in `hw_led_config.h`; OLED pins are not exposed here.

`noob-neoctl led-set 23 0` switches physical pin 23 OFF; `led-set 23 1`
switches it ON. `led-status 23` reads its held output. Native equivalents:
`CALL LED_SET 23 0`, `CALL LED_STATUS 23` (or CALL_MIXED with empty ASCII).
Other pins are untouched. Unclaimed status returns unknown without driving it.
GPIO failures include errno; an already-owned pin is never stolen.

At startup `noob-gpio-init.service` briefly sets pin 23 LOW before noob-neod.
The daemon's first hardware action claims it LOW and holds it, independently
of network readiness. Other LED pins are claimed LOW only on their first SET.
This software does not guarantee the electrical state before Linux starts or
during the short handover; a hardware pull-down is needed for that guarantee.
Stopping the daemon releases its pins. Direct gpioset tests must not compete
with the daemon; use LED_SET instead. Restarting resets pin 23 LOW.

ESP proxies: `NEO_LED_SET` (275) takes physical pin and 0/1;
`NEO_LED_STATUS` (276) takes physical pin. Firmware deployed 2026-10-05.
BLE CLI: `irisctl neo-led 23 1`, `irisctl neo-led 23 0`,
`irisctl neo-led-status 23`. The ESP's native USB must connect to Neo.
VM SYS and normal sequence channels use the same registry. Example mixed
sequence: slot 0, 100ms, 10 bits, physical pin 23 fixed, bit appended:

```
CALL_MIXED SEQUENCE_SET 0 100 275 10 682 1 23 ""
```

Compile Neo endpoint including both hardware modules:
`cc -O2 -Wall -Wextra -Werror noob-neod.c hw_display.c hw_led.c -o noob-neod`.
Install `71-noob-gpio.rules` into `/etc/udev/rules.d/` to grant only gpiochip0
access to the runtime's noob group. Install both service files in
`/etc/systemd/system/`; reload udev/systemd and enable noob-gpio-init.

Verified 2026-10-05: both startup units restarted successfully; pin 23 read
LOW before commands. All ten individual SET ON/OFF calls passed and were left
OFF. Pin 7 changed without changing pin 23. Host ioctl regression and strict
Neo compilation passed. ESP application flashed with verified hash; settings
and SD programs preserved. BLE PING and restored police-on-all status passed.
End-to-end BLE -> ESP -> Neo SET/STATUS/OFF passed for all ten physical pins.
The 76-byte VM diagnostic completed ten pin-23 sequence steps, ending LOW;
r2=8 and dropped=2 confirm the bounded result queue. Police-on-all was restored
with 138 bytes and startup autorun enabled. Full pre-update partition backup is retained
under `iris/build/led-flash-backup.7UpI6b/application-460800.bin`.
These are API/electrical-driver checks, not visual confirmation of each LED.
