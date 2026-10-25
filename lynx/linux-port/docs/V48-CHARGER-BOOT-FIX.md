# V48 charger boot fix — Alpine boot verified on Lynx

On 2026-10-25, V48 was flashed to `boot_a` and booted on the OnePlus Nord 3.
Pinned SSH verified the exact V48 BusyBox init at `192.168.100.7:22`, then
Alpine 3.24.2/OpenRC on `192.168.100.7:2222`. All eight default services
reported healthy, and a ten-sample stability watch passed 10/10 checks.
Battery capacity rose from 29% to 30% while the pack cooled to 28.0°C.
The previous V48 trial checked only `.8`; that observation
missed the actual `.7` address and did not establish a boot failure. The
current trial receipts are `logs/v48-boot-a-trial-1792948228582606428/`,
`logs/v48-first-boot-1792948259460925317/`, and
`logs/v48-stability-1792948664611119402/`.

## Reason

The exact V47 boot image shuts Lynx down when a charger reports `online=1`.
Its PID 1 script checks during boot and has a five-second background watcher.
After those checks, the health startup script in the boot supplement refuses
to run if the charger is online. The three gates together make a cable-woken
shutdown cycle plausible. This is source review, not proof of the cause of
the latest black-screen event.

The V47 local Wi-Fi path does not transmit the earlier UDP beacon; missing
beacons cannot diagnose that boot.

## Exact change

- V48 edits `/init` to remove the boot-time charger poweroff block and the
  five-second charger guard.
- V48 edits `usr/libexec/lynx/autonomous-health-start.sh` to allow the health
  monitors to start while charging.
- The stock kernel, command line, other ramdisk and supplement members, and
  image bytes beyond the supplement remain identical to V47.
- Battery and thermal watchers remain present. They started and reported
  healthy in the first V48 boot; charging protection and long-duration
  behavior still need verification.

The persistent Alpine battery reserve service can still request shutdown at
critical capacity (10% or below), on high battery temperature, or if gauge
readings fail. V48 does not disable those protections. If charging does not
actually replenish the pack, a low-battery shutdown cycle can still occur.

## Optional 98% charging cap, prepared separately

`linux-port/lynx-charge-cap.sh` and `linux-port/openrc-lynx-charge-cap` are
prepared but **not installed or enabled on Lynx**. A host fixture test is
`tools/test_lynx_charge_cap_offline.py`. The controller requests charging off
at 98%, and requests it back on at 95% only below 35°C. It never asks the
phone to shut down. The OpenRC service is deliberately not part of the V48
boot image, so an unverified charge-control write cannot affect the first
recovery boot.

The matched MT6375 kernel source maps a write of `0` to its power-supply
`status` property to `mt6375_chg_enable_charging(false)` and a write of `1`
to `true`. It exposes that property as writable in
`drivers/power/supply/mt6375-charger.c`. V46 live inventory found
`mt6375_charger` loaded and the supply named
`11e01000.i2c:mt6375@34:chg`. The V46 supply read `Not charging` while
gauge capacity rose, so the status text cannot verify the effect of a write.
The exact live binary equivalence and effective charge-current response
remain unverified.

Before enabling the optional cap, first run the controller's read-only `--probe` on
Lynx and inspect the actual driver path, writable attribute, gauge identity,
current, capacity, and temperature. Then perform a monitored one-shot control
trial at a suitable charge level, verify the gauge-current trend over several
samples, and only then install and enable the OpenRC service. If the control
does not work as expected, leave the service disabled. The 98% cap is a
software policy and cannot act while Lynx is off or her Linux kernel is hung;
hardware charging protections remain necessary.

The initial init-only artifact was superseded after the health startup gate
was found. It is retained under
`artifacts/no-charger-shutdown-v48-superseded-offline/` for traceability and
must not be flashed.

## Artifacts and receipts

V48 candidate:
`/noobia/lynx/linux-port/artifacts/no-charger-shutdown-v48-offline/nord3-no-charger-shutdown-v48-untested.img`

SHA-256:
`ff1244698cf791546b7c03c2f510882048c91a88f9344e80d583fda388f2340d`

V47 rollback:
`/noobia/lynx/linux-port/artifacts/wifi-dhcp-retry-v47-offline/nord3-wifi-dhcp-retry-v47-untested.img`

SHA-256:
`c969e1938b051ab03b49ad4f2260e900e9e336997d1026ca00c3a493dedde066`

Build and validation receipts, source snapshots, and two unified diffs are
in `artifacts/no-charger-shutdown-v48-offline/`. The independent validator
checked image size, the exact V47 parent and stock kernel, the precise three
primary member changes, the single supplement script change, payload hashes,
unchanged tail, shell syntax, and the existing host AVB boot model in locked
and unlocked states. The AVB result matches the V47 model: the unlocked model
loads the boot partition; the locked model rejects modified boot content.
Offline validation alone did not establish hardware boot; the later pinned
SSH trial above did.

The builder and validator are:

```sh
python3 /noobia/lynx/tools/build_v48_no_charger_shutdown.py
python3 /noobia/lynx/tools/validate_v48_no_charger_shutdown.py
```

The builder refuses to overwrite an existing candidate. Do not rerun it over
the reviewed artifact.

## Repeat trial and rollback procedure

1. Obtain a fresh power observation. The old 38% reading is stale. Keep Lynx
   cool and let her charge before any boot partition write.
2. Put Lynx in Fastboot on Nexus USB. The trial tool runs the pinned read-only
   identity, active-slot, and partition preflight before any write.
3. Review the exact commands offline:

```sh
python3 /noobia/lynx/tools/lynx_boot_a_v48_trial.py --prepare
```

4. After a fresh charge observation, flash **boot_a only**:

```sh
python3 /noobia/lynx/tools/lynx_boot_a_v48_trial.py --flash-v48 --charged-confirmed
```

The 2026-10-25 trial used `--battery-unknown-accepted` at Noob's explicit
request because Fastboot exposed no battery level. The first Alpine gauge
reading after boot was 29%; the flag records uncertainty rather than claiming
the battery was charged.

The command returns a `result.json` receipt and leaves Lynx in Fastboot.
Check `v48-flashed-no-reboot` before issuing the separate reboot:

```sh
python3 /noobia/lynx/tools/lynx_boot_a_v48_trial.py \
  --reboot-after-v48 --flash-receipt /noobia/lynx/logs/v48-boot-a-trial-.../result.json
```

After reboot, check for pinned SSH on ports 22 and 2222, current battery
capacity, actual charger `online` and charging status, battery/CPU temperatures,
and the health services. Stop the trial if she heats unexpectedly or the
health monitors fail. Unplug or power off as the physical override.

If V48 fails but Fastboot remains available, restore the exact V47 image to
`boot_a`, without changing slot or any recovery partition:

```sh
python3 /noobia/lynx/tools/lynx_boot_a_v48_trial.py --restore-v47
```

The equivalent pinned Fastboot restoration command is:

```sh
/noobia/lynx/tools/platform-tools/fastboot -s 89BYAY5L4T9HFUOV flash boot_a \
  /noobia/lynx/linux-port/artifacts/wifi-dhcp-retry-v47-offline/nord3-wifi-dhcp-retry-v47-untested.img
```

V47 itself still has the charger-triggered shutdown policy, so recovering to
V47 may require booting without a charger. Stock firmware and the older V33
rescue image remain available as further recovery routes. Do not assume V48
is safe for unattended charging until a live monitored trial confirms it.
