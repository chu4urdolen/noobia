# Temperature/humidity sensor probe — GPIO 15

Status: wiring noted, driver not yet enabled.

GPIO 15 is currently connected to an external Iris LED. The active Iris
firmware does not expose a temperature/humidity native function, and a single
data pin is not enough to identify the sensor protocol. Do not run a pull test
or drive this pin until the sensor marking is known.

Likely single-wire parts such as DHT11, DHT22/AM2302, and newer I2C parts such
as AHT20 require different drivers and wiring. The sensor model, supply
voltage, ground, and whether its data line has a pull-up must be recorded
before adding a reusable native service.

Safe next probe:

1. Disconnect the GPIO15 LED while testing the sensor.
2. Record the exact marking on the sensor/module.
3. Add a generic native `TEMP_HUMIDITY_READ` service selected by protocol and
   pin/address; keep acquisition out of VM bytecode.
