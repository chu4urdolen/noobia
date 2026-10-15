# Verified: SoC, CPU, GPU and memory temperature readings

The short supervised cold boot reached pinned SSH on the unchanged V19 image.
After arming an independent stop timer, the coordinator transferred the RAM
pack and inserted only `nvmem_mtk_devinfo` and `soc_temp_lvts`. Both returned0,
and both expected platform-driver bindings appeared. No partition changed.

The resulting snapshot had **29 valid readings out of43 zones**, including:

| Sensor | Reported temperature |
| --- | --- |
| soc_max | 34.917°C |
| CPU sensors | about26.7–35.2°C |
| GPU sensors | about24.2–24.6°C |
| DRAM sensors | about25.6–26.9°C |
| Connectivity | 29°C |

Readings were sequential, so the displayed soc_max need not equal the largest
later per-core sample. These are driver-reported values, not independently
checked thermometer measurements. Battery, board ADC and PMIC zones remain
unavailable; CPU frequency control and throttling were not tested.

The key missing prerequisite was the device-tree calibration provider
`nvmem_mtk-devinfo.ko`, which is absent from the sensor's ELF dependency list.
The published provider source registers read-only NVMEM backed by the
bootloader's `atag,devinfo`. Runtime bounds checks preceded module insertion.
The sensor logged `LK init LVTS`, indicating reuse of bootloader sensor setup.
No fake-calibration warning was observed in the saved kernel stream.

Sensor-stage insertion and checks completed in0.52s. From first beacon to
the explicit shutdown request was about5.1s; phone uptime at the final sensor
snapshot was98.58s. This avoided another prolonged unattended Linux session.

The power-off command timed out after5s as SSH stopped responding. That alone
does not prove physical shutdown. The independent90s shutdown request was
already armed and never cancelled. Physical confirmation was requested from
Noob; until confirmed, treat the power state as unknown and do not start
another hardware operation.

## Evidence and repeatability

Private raw receipt: logs/sensor-trial-1792100424200752360/result.json.
Raw command outputs, stderr, command timestamps, partial/timeout states and
kernel output remain beside it. The kernel stream includes non-UTF8 vendor
log bytes; the summary parser tolerates them while verifying original byte
hashes. It does not alter or republish the raw capture.

`tools/summarize_sensor_trial.py` verifies command capture hashes, pinned native
identity, module return status, DT bindings, timer-before-insertion order and
unchanged V19 image hash. Sanitized readings are in SENSOR-HARDWARE-RESULT.json.
The module pack SHA256 is
`edc011a45072b6c3baa13da4ba73462d7a0e049236719a54fb093fb2da0ebffb`.

The previously prepared43-module pack is preserved but is not the revised
44-module sensor trial. Its review hold remains intact. The global flash hold
also remains active. RAM-loaded modules disappear when Lynx powers off; no
new bootable image or persistent sensor startup is claimed.

Primary source review is recorded in SENSOR-TRIAL-REVIEW.md. Remaining work is
reviewing CPU-frequency control and obtaining battery/gauge temperatures,
using the new working SoC readings for short supervised diagnostics.
