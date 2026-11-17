# First supervised sensor trial after cooldown

Noob confirmed Lynx cooled and asked to continue. This trial uses the installed
V19 boot image and adds only a read-only calibration-data provider and stock
LVTS sensor module in RAM after pinned SSH. CPU frequency, battery and charging
stages remain excluded. The global Linux-flash hold is unchanged.

The earlier prepared pack omitted a DT provider not represented in the sensor
module's ELF dependency list: `nvmem_mtk-devinfo.ko`. It supplies the sensor's
`e_data1..3` calibration cells from `/chosen/atag,devinfo`. The revised pack
loads this provider before `soc_temp_lvts.ko`, validates the boot tag bounds,
and checks the three cell definitions. No fuse programming is performed.

Primary reference sources were saved from OnePlus kernel commit
81ec42ad5e803be0cba619f9f7bb298db7d33d7b, under
docs/thermal-probe-sources-1792099510456502963. `mtk-devinfo.c` registers a
read-only NVMEM provider with no write callback. `soc_temp_lvts.c` obtains the
clock, resets, interrupts and calibration before initialization; normal probe
initializes the sensor and its hardware thermal reboot protection. Module
insertion is not a read-only operation even though the calibration provider is.
Published sources are a reference, not independently proven exact OEM binary
provenance. The actual modules remain unmodified, matching stock artifacts.

Clock/reset/project prerequisite modules were present in the saved V19 session.
Runtime guards require them again. DT argument cells were not treated as
independent phandles: the LVTS clock is provider0x3c/index2; resets are provider
0xca/indices0and1. The nvmem cell provider is `/efuse@11ee0000`.

Revised pack: thermal-ssh-pack-1792099635423460996,2294722bytes/44modules,
SHA256 edc011a45072b6c3baa13da4ba73462d7a0e049236719a54fb093fb2da0ebffb.
Only the sensor stage has a runnable plan. Native ARM guard tests
1792099651403112156 passed all six refusals and unchanged module inventory.

The trial coordinator is tools/lynx_sensor_trial.py. It starts the UDP listener
before power-on, verifies pinned SSH identity, uploads an independent90second
stop script, and arms it BEFORE acknowledging/cancelling V19's normal fallback.
It then transfers the pack, captures before/after data, loads only the sensor
stage, captures dmesg and requests power-off immediately. The independent stop
timer is never cancelled. No partition write, reboot, charging change or CPU
module load is included.

The detached BusyBox timer survived parent exit and reached kernel power-off
in the exact stock-kernel ARM VM (1792099829723111225, delay accelerated90→1s).
This does not prove physical PMIC shutdown or protection against a kernel hang.
Noob must remain present with the physical power-off override. Loss of SSH is
not proof of power-off. All raw command streams, timeouts and phase timestamps
are saved under logs/sensor-trial-*. No GitHub upload during preparation.
