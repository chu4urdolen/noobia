# DHT11 on Iris — 2026-09-19

Confirmed wiring: DHT11 data GPIO15; LEDs GPIO16 (channel 0) and GPIO40
(channel 2). The earlier note incorrectly assumed the old LED wiring.

Firmware `0.2.9-dht11` adds `CALL TEMP_HUMIDITY_READ [0|1]`, native ID 190.
The optional selector returns temperature or humidity in tenths; reply detail
contains both values and all five raw bytes. Configuration does not touch the
pin at boot. Reads enforce a two-second interval, use an open-drain start
pulse, bound pulse waits, and reject idle-low, timeout, checksum and range
errors. The service lives in the reusable runtime; only Iris defines GPIO15.

Timing and byte decoding were checked against Adafruit's reference driver:
https://github.com/adafruit/DHT-sensor-library/blob/master/DHT.cpp

Commands on Nexus:

    /noobia/iris/tools/irisctl dht-read
    bash /noobia/iris/diagnostics/dht11_ble.sh
    /noobia/iris/tools/irisctl vm-load dht11_once
    /noobia/iris/tools/irisctl vm-run
    /noobia/iris/tools/irisctl vm-status

The diagnostic script lights both LEDs, tries three readings with 2.1-second
pauses, checks PING, and turns LEDs off on exit. It returns nonzero on failures.
The VM waits 2100ms, calls native 190 into r0, then halts on success. Sensor
errors become VM faults instead of invented readings.

## Hardware result

### Retest after wiring correction

After the user corrected swapped VCC/GND wiring, three BLE reads passed:

| Temperature | Humidity | Raw bytes (checksum included) |
| --- | --- | --- |
| 26.0 C | 62.6% | 3e061a005e |
| 25.8 C | 58.8% | 3a08190863 |
| 25.8 C | 58.8% | 3a08190863 |

The same nine-byte VM then completed with `state=HALTED pc=9` and `r0=258`
(25.8 C). Both LEDs on GPIO16/40 were left on as requested. These tests
verify sensor communication and checksum validation, not measurement accuracy.

### Initial test before wiring correction

The build passed (1,365,799 bytes, 43% of the app partition); flashing over
USB UART verified all hashes. BLE INFO confirms `0.2.9-dht11`.
Both LED commands report their requested output levels on GPIO16/40.
The first read and all three subsequent diagnostic reads returned
`DHT11 idle_low`. PING still returns PONG. No temperature/humidity measurement
has passed yet: the data line remains low with INPUT_PULLUP before the start
pulse. This does not identify whether wiring, power or the sensor causes it.
The nine-byte VM uploaded and ran, then reported `state=FAULT pc=8` with
`syscall 190: DHT11 idle_low`, confirming native dispatch and error propagation.
Both LEDs were turned off after the tests.

Next: check the sensor's labelled DATA/S connection to GPIO15, VCC to 3.3V,
and GND to Iris GND. Do not infer a module's pin order from its appearance.

## Source provenance

The working firmware had changes absent from Git. This check-in synchronizes
its lazy I2C registration, corrected LED handling, runtime service updates and
DHT11 addition. Credential files are excluded from that synchronization.
