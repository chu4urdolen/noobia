# Live battery telemetry and repeatable native SSH sessions

Lynx now runs our read-only battery monitor on the matching OEM kernel. The
fixed DeviceType query returned **0xa5ff**, the ZY0603 family in OnePlus's source.
The monitor then exposed fresh temperature, pack voltage, signed gauge current
and state-of-charge readings over native SSH. Rebooting unchanged V19 and
running the complete RAM setup again succeeded.

| Initial snapshot | Battery | Charge | Pack voltage | Signed gauge current |
| --- | --- | --- | --- | --- |
| First monitor session | 26.4°C | 96% | 8.595 V | −282 mA |
| Repeated boot/resume | 22.1°C | 91% | 8.440 V | −265 mA |

Negative gauge current denotes discharge in this interface. These are individual
observations, not measured idle-power averages or battery-life estimates. The
first session preserved 109 host samples before Noob manually restarted into
Fastboot. The current session has a fresh host log and no routine shutdown.

## What the code reads

`lynx-battery-monitor.c` supports only the confirmed ZY0603 client at stock DT
path `/i2c@11d04000/bq27541-battery@55`, adapter 7/address 0x55. Initialization
requires explicit read permission and the previously queried DeviceType. Each
`battery_snapshot` read serializes four standard read-word operations:

| Register | Meaning in the matching OEM family path |
| --- | --- |
| 0x06 | Temperature, stock rounded kelvin conversion |
| 0x08 | Pack-voltage word, mV |
| 0x0c | Signed current, mA; negative is discharge |
| 0x2c | State of charge, percent |

There are no gauge command/configuration writes, retries, charging routines,
calibration, register scanning or automatic aliases in the monitor. The normal
SMBus read sends its register-selector byte. Each field has an explicit error
code; failed reads are not replaced with cached plausible values. A mutex
serializes concurrent sysfs snapshots.

The identity module is separate: it sends only the reviewed DeviceType selector
0x0001 to control register 0x00, then reads the reply and unloads. See
[its review](GAUGE-IDENTITY-TRIAL.md). It does not load the OEM charging bundle.

Temperature uses `(raw - 2731) * 100` millidegrees, matching the OEM rounded
conversion. The optional OEM balancing-temperature compensation is absent.
Pack voltage is not individual-cell or cell-imbalance telemetry. No external
temperature calibration, charging safety validation or stress test is claimed.

## Continuous session policy

Noob explicitly revoked the earlier 90-second/end-of-test shutdown policy and
authorized ongoing development over SSH with USB unplugged. The current
`--keep-running` profile arms a temperature observer before acknowledging the
boot fallback, loads the sensors and CPU controls, performs the identity query,
and leaves SSH running. It does not arm the old stop timer or request power-off
on successful completion or an ordinary test failure.

`thermal-watch.sh` samples SoC/CPU readings every five seconds and requests
shutdown at 60°C. `battery-watch.sh` reads one fresh battery snapshot every five
seconds and requests shutdown at 45°C battery temperature. Missing/invalid
temperatures are logged as unavailable. These are conservative development
cutoffs, not factory thermal policy; a kernel hang can defeat software shutdown.
The display remains uninitialized and a black screen does not establish power
state. The battery tools do not change deep-idle or charger settings. A separate,
verified [WFI fallback](IDLE-POWER.md) now disables repeatedly rejected deep CPU
idle states in the current RAM session, with the original flags saved for undo.
The separate [soft-throttle watcher](COOLING-CONTROL.md) requests the tested
one-step CPU cooling limit at 45°C and releases it at 40°C or lower. Its decision
logic passed on host and native BusyBox; no heat-triggered hardware test was
performed. Neither addition is part of the unchanged V19 boot image.

`collect_battery_session.py` saves cached observations to the host every ten
seconds, including timestamps, hashes, failed-command captures and identity
proof. Its bounded one-hour logger ending does not stop Lynx or her RAM watchers.
All raw captures, module binaries and build inputs remain local/private.

## Repeat without flashing

From `/noobia/lynx`, with the private, hash-pinned inputs present:

```sh
python3 tools/resume_battery_session.py --start --usb-unplugged-confirmed
```

The optional `--runtime-power` stage also installs/verifies the tested WFI
fallback and soft-throttle watcher after both temperature watchers are ready.
See [runtime power setup](RUNTIME-POWER.md) for its validation and fresh-boot
test limitation. The default command above retains the original resume path.

Verify the detached listener is ready before booting the existing V19 image.
The resume worker discovers the DHCP address and proves pinned native identity,
loads the unchanged sensor/CPU pack, verifies the gauge reply, checks the exact
monitor source/binary/VM evidence, installs into RAM, starts both watchers and
the host logger, then reports `online`. Any failed step preserves its streams
for review; it does not flash, change slots, reboot or stop the phone.

If already in Fastboot, verify the known serial/product/slot before issuing
only `fastboot reboot`, then unplug USB promptly and continue over Wi-Fi. A
temporary host USB ACL may be needed; that is a host access fix, not a phone
partition operation. The listener should remain ready throughout startup.

After a verified session, `tools/lynx-ssh` selects the newest discovered session
address and retains strict pinned-key, key-only SSH authentication. A reboot
clears the RAM modules/watchers, so use the resume worker again rather than
assuming the previous session's address or modules remain valid.

## Evidence and build reproducibility

Monitor source SHA256:
`24a3c1e82221c70ad0d0bdf17e92ab046f57e4bdd3cf6ff0e40c8e3a5a0b25f8`.
Module SHA256:
`10df9e698e020893e9d28796db8bd1a93ffdd6c2d9779463f678a3687f0c931d`.
Private basis: `artifacts/gauge-module-basis-1792107325426159905`.

The build uses actual embedded stock headers, the exact Android clang release,
unmodified pinned Kbuild and genuine observed stock import CRCs with checked
source export declarations. Full LTO and strict CFI remain enabled. The module
name is distinct from the one-shot diagnostics so they cannot silently replace
the resident battery monitor.

Actual C fixtures passed fixed-register/order/mutex checks, model/default and
client refusals, fresh reads, partial errors, signed-current boundaries and
temperature/range conversions. Exact-stock-kernel ARM VM load/refusal/unload
passed before hardware loading. Shell watcher tests cover normal, cutoff,
invalid, negative, missing and failed readings with mocked power-off. Failed
builds/tests remain preserved, including a kernel macro name collision and an
unsupported ushort parameter interface; the final uint interface has genuine
stock symbol-version evidence. No checks or protections were force-disabled.

First hardware install: `logs/battery-monitor-install-1792107625689113056`.
Repeated full resume: `logs/battery-resume-1792171173913624900`.
Repeated install: `logs/battery-monitor-install-1792171660594161155`.
Full resumed proof: `logs/live-resumed-battery-proof-1792171777720519037`.
`tools/summarize_battery_monitor.py` verifies saved stream hashes and successful
identity/install/resume conditions before generating the sanitized
[hardware result](BATTERY-HARDWARE-RESULT.json).

Observed next power-management leads are Wi-Fi power saving initially off and
deeper CPU idle states enabled but unused in the sampled CPU0 counters. Those
observations do not prove the cause of drain; do not force deep idle or load an
unreviewed power-management bundle. V19, stock undo, recovery-related partitions
and slot B remain unchanged; the Linux-flash hold stays active.

## Reversible Wi-Fi power-save check

The pinned MediaTek reference maps enabled power saving with the normal timeout
to `Param_PowerModeFast_PSP`, and disabled to CAM. A 30-second hardware trial
enabled power saving, retained live SSH across six observations, then restored
the original off setting using an independently detached rollback task. That
task only changes Wi-Fi power saving; it never shuts down or reboots Lynx.

The trial battery readings stayed at 23.4–23.5°C and 90% charge. Instantaneous
discharge readings varied with network/host activity, so the short test does
not establish an average energy saving. Normal power saving was then enabled
for the current RAM session and verified over pinned SSH. It is not baked into
V19 or forced into the automatic resume sequence. Deep-idle flags and charging
settings remain unchanged.

Private trial: `logs/live-wifi-power-saving-trial-1792171973859561016`.
Persistent-for-this-session enable: `logs/live-enable-wifi-power-saving-1792172142603499476`.
The source review is preserved under
`artifacts/wifi-power-source-review-1792107802822693331`.
