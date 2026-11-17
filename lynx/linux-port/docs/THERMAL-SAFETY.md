# Thermal safety hold after the first native Linux session

Current follow-up: [live battery monitoring](BATTERY-MONITOR.md) now works,
including confirmed ZY0603-family readings, CPU/SoC sensors and frequency
controls. Noob authorized continuous USB-unplugged development and revoked
unconditional timed shutdown. Temperature-triggered watchers remain active.
The Linux-flash hold and incomplete overall thermal validation remain in place.
The findings below describe the original missing-driver state and history.

Noob reported Lynx heating up after the successful V19 SSH session. Read-only
diagnostics at about6219s uptime found:

- No battery power-supply device, battery temperature or battery capacity.
- Only the MT6375 charger supply, reporting `Not charging`, `online=0`,
  `type=Unknown`. This is incomplete driver telemetry, not proof that power
  is disconnected or the battery is safe.
- 42 of 43 thermal zones returned EINVAL for temperature. Only `consys` returned
  33000millidegrees (33°C). That is not the battery or CPU temperature.
- No exported CPU frequency policy directories and no thermal cooling devices.
  CPU frequency/throttling could not be verified.
- CPU samples showed99–100% idle. Load average2.00 included blocked kernel
  tasks and did not establish CPU saturation. Low utilization does not prove
  that missing frequency/idle/power controls are harmless.

The live command changed no partitions, module state, charging controls or
thermal settings. It has completed. Earlier read-only raw inventory remains
under logs/live-inventory-1792098110330311623; the later heat check was visible
in the tool transcript and summarized here, not saved as a new full raw file.

## Immediate action

Stop hardware development tests. Unplug external USB power and power Lynx off
to cool. A black screen alone is not verified power-off. Follow the observed
button notes or the stock recovery Power off option if necessary; do not
select Format data. Do not leave V19 running unattended or charging while
battery temperature and thermal protection remain unverified.

The V19 image, stock undo, private input cache, complete kernel logs and runtime
journals are already saved. No further phone operation is needed to preserve
the milestone. Offline source/module analysis can continue while she is off.

## Before another extended run

Review the matching stock CPU-frequency/idle, thermal sensor, battery/gauge,
charger and Type-C module dependencies and DT bindings. Establish trustworthy
battery/CPU temperature and throttling readings in a short supervised run.
Do not guess register values, force charging, disable thermal controls, or
load an unreviewed bundle of power-management modules onto a hot phone.

V19 remains the first networking milestone, not a thermally validated daily
operating image. The fixed V19 Linux flash command is held pending review;
stock restoration remains available.

Noob subsequently confirmed USB was unplugged and Lynx was shut down. No further
phone commands are being sent. Continue offline until a reviewed supervised
thermal test is ready.

## Offline dependency findings

The matching kernel enables CPU-frequency and thermal frameworks, but builds
the MediaTek hardware drivers as modules. Saved live module inventory confirms
the following were absent:

| Function | Matching stock module | Missing modules in its dependency closure |
| --- | --- | --- |
| CPU frequency control | `mediatek-cpufreq-hw.ko` | 2 |
| SoC temperature sensor | `soc_temp_lvts.ko` | 1 |
| Thermal integration | `thermal_interface.ko` | 11 |
| Board ADC temperatures | `thermal-generic-adc.ko` | 1 |
| Battery/gauge integration | `mt6375-battery.ko` | 9 |
| OPLUS charging integration | `oplus_chg.ko` | 8 |
| Type-C controller | `tcpc_mt6375.ko` | 1 |

All dependencies resolve to local matching stock module files. The audit
normalizes kernel module hyphen/underscore names and compares against the saved
live inventory. `tools/audit_thermal_dependencies.py` reproduces this offline.
The first audit's name-normalization error and its corrected result are both
preserved locally. This is a review checklist, not an approved load sequence.

PSCI CPU-idle support is compiled in; actual deep-idle operation was not
measured. Missing CPU-frequency policy directories do not establish the current
CPU clock. Missing modules plausibly explain unavailable interfaces, but no
specific cause of the reported heat has yet been established.
