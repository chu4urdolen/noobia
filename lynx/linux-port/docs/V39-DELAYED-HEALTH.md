# V39 delayed-health diagnostic — prepared offline

V38 proved Lynx could run the stock kernel, BusyBox, Wi-Fi, pinned SSH, and
small checksummed ext4 stage writes through uptime 190 seconds without health
startup. The failed V36 autonomous run lost SSH after its health path started,
but its pstore did not identify a reset cause. V39 asks a narrower question:
**does the same packaged V31 health path complete if it starts only after a
proven 190-second Wi-Fi window?** It does not attempt an Alpine handoff.

V39 derives from exact V38 and changes only the primary `/init` tail. The
stock kernel, command line, entire supplementary payload (including the
reviewed V31 health scripts and modules), AVB footer, and other ramdisk
members are byte-identical. It retains V38's verified Wi-Fi/SSH startup and
checksummed records on the exact `LYNXROOT` ext4 filesystem. It records
`HEALTH_BEGIN` before calling the existing local health startup, then either
`HEALTH_FAILED` or `HEALTH_READY`. A successful run keeps BusyBox as PID 1,
checks the health supervisor every five seconds, records `END` at or after
uptime 300, and requests power-off. An independent timer requests power-off
420 seconds after the tail begins if the main path stalls. A separate
five-second charger guard requests power-off if charging becomes active or
charger state becomes unreadable while health starts. This is a bounded
diagnostic, **not** a daily boot image.

The image is private at
`linux-port/artifacts/delayed-health-v39-offline/nord3-delayed-health-v39-untested.img`,
SHA-256 `0eaee951ce85918f5c6c4f6f88cf79ddba40485755df730103d390025a172f49`.
Build and independent validation receipts are in the same artifact directory.
Validation checked exact V38 parent, unchanged stock kernel and supplement,
packaged V31 health script bytes, init-only round trip, BusyBox syntax,
persistent log and charger guards, AVB model behavior, and exact V33/V19
rollback images. `tools/lynx_boot_a_v39_trial.py --prepare` passed without
phone contact. A three-second read-only collector dry run on the current V33
Alpine boot correctly reported `candidate_seen=false` at
`logs/v39-health-window-1792615693644410052/result.json`. The V39 record
parser fixture passed at `logs/v39-parser-fixture-1792615703552728891/`.

The following paragraph records the preparation state before the hardware
trial. Offline validation cannot establish whether autonomous
health startup will complete, whether a module can reset the phone, whether
the persistent write survives such a reset, or whether the power-off path
will behave as expected. The existing V33 and V19 rollback images remain
verified. Any hardware trial requires a fresh Fastboot preflight, a pinned
collector started before `boot_a` is written, a separate reboot, prompt USB
removal, and a fresh V33 restoration after the diagnostic. Preserve slot B,
bootloader, recovery, and all other partitions.

For the next trial, use `tools/capture_v39_health_window.py` and the guarded
`tools/lynx_boot_a_v39_trial.py`. If contact ends unexpectedly and Lynx
returns to Fastboot, capture the read-only preloader/LK log before restoring
V33. After V33 Alpine is verified, the existing
`tools/capture_v38_persistent_trace.py` can retrieve V39's stage records from
the same boot-ID-scoped directory. A record ending at `HEALTH_BEGIN` would
bracket failure inside or immediately after autonomous health startup; a
`HEALTH_READY` record would prove that startup returned successfully. Neither
alone identifies a kernel or hardware root cause.

## First hardware attempt — health child ready; contact lost

The exact image was flashed only to `boot_a` after a fresh identity/layout
preflight, then rebooted separately with the collector already listening:
`logs/v39-boot-a-trial-1792615809503827990/result.json` and
`logs/v39-boot-a-trial-1792615817975780981/result.json`. Noob unplugged USB.
Pinned SSH matched V39's exact `/init` hash on boot ID
`30131789-21c8-4367-8c45-4fadc37ef7dc`. Seventy-nine complete samples
span uptime 93.49–195.48 seconds. `HEALTH_BEGIN` appears at 190.84. By the
last successful sample the V31 health child had loaded battery and thermal
modules, reported `READY_ON_PHONE_MONITORING_ACTIVE`, left a zero child
result and a `ready` file, with battery temperature 24.4°C and a passing
supervisor sample. The parent had **not** logged `HEALTH_READY`. The next SSH
attempt failed. No subsequent pinned contact appeared through the independent
V39 safety deadline. The raw snapshots and preliminary incident summary are
at `logs/v39-health-window-1792615806259628878/`.

The recovered persistent stage file resolves the immediate exit path:
`logs/v38-persistent-capture-1792616489493406914/result.json` verifies
`HEALTH_BEGIN` at uptime 190 and `HEALTH_FAILED` at 195, with no
`HEALTH_READY`. The parent health call returned failure and V39 entered its
deliberate power-off path. The V31 child had already written zero and `ready`,
so the remaining failure is between that child result and the parent's
success return. The exact failed check is not yet recorded. It may be the
parent's final `lynx-health-supervisor.sh --once`; that is an inference, not
an established cause. Do not attribute this to a kernel reset, heat, or UFS
without matching evidence.

While Lynx was in Fastboot, the read-only preloader/LK log was captured at
`logs/pllk-1792616343259834392.json`. It includes UFS and reset entries, but
they may describe Fastboot entry rather than the V39 exit. Fresh Fastboot
preflight passed, exact V33 was restored **only to `boot_a`** without an
implicit reboot (`logs/v34-boot-a-trial-1792616345589715157/result.json`),
and a separate unplugged boot passed pinned SSH, V31 RAM health, V33 handoff,
and independent Alpine/OpenRC PID 1 verification:
`logs/v33-alpine-pid1-verification-1792616485891521272/result.json`.
**V33 is installed and Alpine is last verified running.** Investigate the
parent's failed check before another hardware trial.
