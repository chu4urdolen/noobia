# Argus OLED diagnostics

These tests diagnose the GME128128-01-IIC/SH1107 display on Argus without
mixing diagnostic behavior into Argus's normal services.

## Safe address test

`address_probe.sh` reads the idle state of GPIO2/SDA and GPIO3/SCL, then probes
the standard OLED addresses `0x3c` and `0x3d`. It sends no initialization or
framebuffer data. Ten trials are used by default so intermittent contacts are
visible rather than hidden by one successful transaction.

```sh
./address_probe.sh
```

Optional environment variables are `OLED_I2C_BUS`, `OLED_PROBE_TRIALS`, and
`OLED_PROBE_DELAY`.

## Unmodified upstream test

`upstream_seeed_test.sh` clones Seeed Studio's `grove.py` repository into
`/tmp`, prints the exact commit, and executes its original SH1107G example.
The upstream program briefly draws text and clears the display after three
seconds. Network access and the system `python3`/SMBus package are required.

```sh
./upstream_seeed_test.sh
```

Both scripts temporarily stop `argononed.service` to prevent another process
from using the same I2C bus. A shell trap restarts the service on success,
failure, or interruption.

The earlier low-level C experiments remain in `../../tools/`. They are useful
for controller-level investigation, but the two scripts here are the repeatable
acceptance tests: first establish electrical/address health, then try a known
upstream driver unchanged.
