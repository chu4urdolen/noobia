# Built-in native functions

This is the planning list for functions exposed to the Noob VM. The VM should
contain only portable bytecode and generic calls; timing-sensitive or hardware-
specific work belongs in native services.

## Already present

- Common VM/runtime: `TIME_NOW`, `TIME_RESET`, load/run/stop/reset, calls,
  arithmetic, memory, jumps, subroutines, and nonblocking waits
- Iris hardware: camera, SD/storage, microphone, DHT11, ADC/light sensor,
  ultrasonic ranging, IR transmit/receive, and board/external LEDs
- Wi-Fi connect/disconnect/scan/RSSI and RSSI event gathering
- BLE scan/connect and credential updates
- audio recording, camera MJPEG recording, and persistent VM storage

Iris currently has **no external I2C or OLED capability**. GPIO17 and GPIO18
are occupied by the blue LED and IR receiver. The reusable runtime retains an
I2C implementation for a future Noob or a future Iris wiring profile, but Iris
does not register it and `CAPS` must not report it. There is also no unrestricted
VM GPIO/PWM syscall yet; Iris exposes only named, bounded hardware functions.

## High-value reusable additions

- `DELAY_UNTIL` using the monotonic clock, with wrap-safe deadlines
- watchdog arm/kick/status and brownout/reset-cause reporting
- structured event queue with timestamps and source IDs
- ring-buffer files and atomic append/rename for crash-safe storage
- SHA-256/CRC and signed program/configuration verification
- configuration namespaces with validation and rollback
- UART device channels and framed serial bridging
- SPI transactions with selectable mode, frequency, and chip-select
- I2C bus recovery/status for a Noob that actually registers an I2C bus
- generic sensor polling scheduler with min/max intervals
- battery/USB voltage and temperature telemetry where hardware exposes it
- BLE GATT notifications for logs, status, and event streams
- Wi-Fi credentials provisioning with an explicit factory-reset path
- OTA update staging, hash verification, and rollback

## Iris-specific registrations

Iris may register camera, SD, microphone, and board-specific LEDs or sensors,
but their pin assignments and drivers must remain under `noobs/iris/`.

## Safety rules

- Native calls validate ranges and return structured errors.
- Storage writes use temporary files plus atomic rename.
- Network sniffing/monitor mode is explicit and easy to stop.
- GPIO tests never drive a line unless the caller explicitly requests it.
- Every long-running service has `START`, `STOP`, `STATUS`, and a timeout.
