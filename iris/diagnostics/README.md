# Iris diagnostics

Diagnostics are kept as source and scripts. Generated binaries and result logs
stay local. The current attached-hardware smoke test is:

```sh
./current_hardware_ble.sh [CONFIG]
```

It exercises BLE, both external LEDs, DHT11, the photoresistor ADC, IR
loopback, and ultrasonic ranging. Defaults come from
`../tools/iris-tools.conf`; individual commands also accept their values from
that file. Historical OLED sketches are retained as experiments, not as the
current Iris pin profile. They require a deliberately different firmware and
wiring profile; current Iris has no external I2C capability.
`uart_raw_console.c` is a minimal Linux serial panic/log capture utility used
when BLE transport failures need an independent trace. Build locally with:

```sh
cc -O2 -Wall -Wextra -o uart_raw_console uart_raw_console.c
```

Do not commit the generated binary.
See `MIC_RISE_20260923.md` for the rolling microphone detector hardware test.
