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
current Iris pin profile.
