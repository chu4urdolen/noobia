# Noob ESP32 diagnostics

This reusable library cannot magically detect whether a GPIO is physically
unconnected. Instead, the board definition registers every known reservation
and explicitly allowlists any pin on which a pull-only test is acceptable.

`GPIO_AUDIT` and `GPIO_INSPECT` are passive. `GPIO_PULL_TEST` temporarily uses
the internal weak pulls, never drives an output level, and restores input mode.
It fails closed unless the physical board has allowlisted that pin.

`Esp32SoftI2cDiagnostics` provides an open-drain software address scan for
diagnosing pin routing and hardware-controller conflicts. It never drives an
I2C line high.
