# Prepare power diagnostics after Wi-Fi and SSH

Noob requested Wi-Fi/SSH first so driver failures remain observable. The
prepared approach keeps the existing boot image and transfers a small
diagnostic pack into RAM after pinned SSH identity proof. No extra boot image,
partition write, or automatic boot-time module insertion is needed.

An ordinary failed probe may leave SSH available. A kernel deadlock, crash,
radio reset or power fault can still disconnect it; remote access is not a
hardware safety guarantee. Lynx remains off and the thermal hold stays active.

## Prepared artifacts

`tools/prepare_thermal_pack.py` builds a private artifact under
`linux-port/artifacts/thermal-ssh-pack-*`. The initial pack is2291277bytes,
containing43exact matching stock modules. It verifies the kernel vermagic,
dependency order and overlapping imported-symbol CRCs against the saved live
module set. No CRC conflicts were found. Archive checksums cover every file.

The initial pack SHA256 is
`e68329332419a9a95dbf6bfe0a632fd983272b1c2eb496294b6c1b57e28f4228`.
It contains OEM modules and stays local; only our preparation/runtime/test
source is published.

| Order after confirmed SSH | Group | New modules relative to saved V19 session |
| --- | --- | --- |
| 1 | SoC temperature: `soc_temp_lvts` | 1 |
| 2, only after a valid SoC reading | CPU frequency: `oplus_omrg`, `mediatek_cpufreq_hw` | 2 |
| Review pending | Board ADC temperature | 1 |
| Review pending | Thermal integration | 11 |
| Review pending | Battery/gauge | 9 |
| Review pending | Charging integration | 8 |
| Review pending | Type-C | 1 |

Three enabled stock DT targets match the initial modules:

- `/lvts@10315000`: `mediatek,mt6983-lvts`.
- `/soc/performance-controller@0011bc00`: `mediatek,cpufreq-hw`.
- `/soc/oplus-omrg`: `oplus,oplus-omrg`.

Relevant property hashes are checked before any insertion. DT matches and ABI
checks do not prove that clocks, supplies, calibration or physical probing work.

## Runtime behavior

`thermal-step.sh` defaults to a read-only snapshot. Its plan mode displays the
manifest. Explicit loading is limited to the first two named stages; battery,
charging and integration groups have no runnable load plans yet.

The pack ships with `REVIEW-HOLD`, so loading is currently refused. Do not
delete the hold file as a shortcut: it is covered by the pack checksum. Prepare
a separately reviewed version when the supervised hardware procedure is ready.

Before insertion, the staged runtime requires the correct kernel, a live SSH
session, the current boot's pinned-host acknowledgement, valid pack hashes and
matching DT properties. The CPU-frequency stage additionally requires a
readable `soc_max` value above0and below50000millidegrees. That conservative
test cutoff is not a battery-temperature safety guarantee.

Each stage records a snapshot before/after and a journal entry before each
`insmod`, then its return status. A module-load error stops the sequence.
There is no retry, automatic unload, charger setting, CPU governor write,
thermal-limit change, partition access or stress test. Already loaded
dependencies are skipped. An insertion returning successfully is not treated
as proof of a working sensor or frequency policy.

Runtime journals are in RAM and still need live host capture. A kernel hang
can prevent further logging or shutdown; do not rely on a shell timeout to
cancel a driver blocked inside the kernel. A supervised test and physical
shutdown path remain necessary before any extended run.

## Offline commands

From `/noobia/lynx`:

```sh
python3 tools/prepare_thermal_pack.py
python3 tools/test_thermal_pack.py
```

Or `make -C linux-port thermal-pack thermal-check`. These do not contact Lynx.

Validation checks every archive entry and module hash, kernel version and
dependency order. An isolated ARM VM with the exact stock kernel/BusyBox
passed six actual-shell refusal cases: review hold, unsupported stage, no SSH,
boot-token mismatch, changed/missing pack bytes, and different DT. Its module
inventory stayed unchanged. This verifies the guards, not physical drivers.

## Work before hardware use

Review the initial drivers' stock probe paths, clock/regulator dependencies,
and binding checks; prepare a bounded host log capture and supervised shutdown
procedure. Review battery/gauge and charger side effects separately. Keep V19
unchanged as the networking reference. No reconnection or flash is requested
by this preparation step.
