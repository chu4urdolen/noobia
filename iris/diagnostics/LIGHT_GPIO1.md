# Photoresistor on GPIO1

> GPIO1 remains the current photoresistor assignment. References below to LEDs
> on GPIO16/40 describe older wiring; current LEDs are GPIO17/47.

The user connected a three-pin light module with S on GPIO1. Exact module
model and light-to-voltage direction are unconfirmed. GPIO47 is no longer
the signal connection. Use 3.3V module power and a common ground.

`0.2.10-light` adds a reusable ESP32 ADC service. Iris registers channel 0 as
GPIO1; other ADC channels remain unregistered. Registration does not start
the ADC. A persistent oneshot handle is retained per ADC unit and each channel
configuration is cached. Each call performs 1..64 reads; failures report the SDK
error.

- `CALL ADC_READ 0 [samples]`: native 191, raw mean of registered channel 0.
- `CALL LIGHT_READ [samples]`: native 192, Iris's light channel convenience call.
- `irisctl light-read [samples]`: BLE command, default 16 samples.
- `bash /noobia/iris/diagnostics/light_ble.sh`: five readings, both LEDs left on.
- `irisctl vm-load light_once`, then `irisctl vm-run`: native 192 into r0.

ADC counts range from 0 to 4095 with 12-bit conversion and 12dB attenuation.
Details include pin, mean, min, max and sample count. Counts are not lux;
cover/uncover testing establishes the direction and useful working range.
Zero/full-scale can be a real rail voltage and is not by itself proof of
either sensor presence or sensor failure.

Reference: https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/peripherals/adc_oneshot.html

## Verification

Build passed: 1,373,499 bytes (43% of app partition), 62,544 bytes global RAM.
Flashing via USB UART verified hashes; BLE INFO returned `0.2.10-light`.
Five batches of 16 samples returned mean 0, minimum 0, maximum 0..5.
The six-byte `light_once` VM halted normally with r0=0. Sample count 65 and
unregistered channel 1 were rejected; a subsequent valid light read succeeded.
Both LED outputs report high on GPIO16/40; PING returns PONG.

The DHT11 regression check now returns `idle_low` on GPIO15, whereas it passed
before the photoresistor was attached. The cause is not established. Neither
reading establishes a working photoresistor: a near-ground signal can result
from lighting, wiring, power or the sensor. Next test is a controlled change
in illumination and a check of the shared module supply/ground connections.
## Current dynamic detector

Firmware 0.4.6 samples GPIO1 every 250 ms through the reusable common change
thread. Its first reading is a runtime baseline and the default event threshold
is a 200-count delta. While LED sequence channels 0 or 1 are busy, the thread
remains running but performs no ADC sample. The first post-sequence reading is a
fresh baseline. Live verification observed no queued light event after a full
police sequence.
