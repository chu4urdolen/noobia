# V41 parent-only health retry — offline candidate

V40's unplugged hardware trial produced neither pinned SSH contact nor a
checksummed `START` stage file. Its new supplementary payload passed an offline
BusyBox CPIO extraction test, but an early payload or storage failure remains
possible. The first V33 restore boot also lacked contact; a second boot reached
Alpine. This makes one unsuccessful V40 boot inconclusive.

V41 uses exact V39 as its parent and leaves **every byte after the AVB-covered
primary region unchanged**, including the V39 supplementary payload, health
child, modules, and recovery-related bytes. The only changed primary member is
`/init`. It retains V40's bounded stage writer and observation window, but
sources V39's original health handoff script. If that script returns failure
after the child has reported zero and created its ready marker, PID 1 samples
the existing health supervisor at most twice more, one second apart. If either
sample passes it records `HEALTH_READY`; otherwise it records
`HEALTH_FAIL_POSTCHECK`. Other handoff failures record `HEALTH_FAIL_CHILD`.
The independent charger guard, 420-second outer power-off timer, and final
power-off at uptime 300 remain. There is no Alpine handoff.

The offline image is
`artifacts/health-primary-v41-offline/nord3-health-primary-v41-untested.img`,
SHA-256 `9a1bb4e1a3a5cc89ff910dbdc2013868a28063c2a3dbc1fa7f1f0f040d521776`.
Its build and independent validation receipts sit beside it. Validation
confirmed BusyBox syntax, exact V39 supplement bytes, stock kernel and command
line, only `/init` changed in the primary CPIO, V33/V19 rollback hashes, and
the pinned AVB model for unlocked and locked cases. The builder is
`tools/build_health_primary_v41.py`; the validator is
`tools/validate_health_primary_v41.py`.

The guarded `tools/lynx_boot_a_v41_trial.py --prepare` check passed with
the exact V33 restore command held ready. The preboot
`tools/capture_v41_health_window.py` completed a one-second dry run against
live V33, capturing one pinned SSH sample and correctly reporting no V41
candidate: `logs/v41-health-window-1792618047207811799/result.json`.

## Controlled hardware trial — recovery pending

After a fresh Fastboot identity/layout preflight, V41 was flashed **only to
`boot_a`** and rebooted with the collector already running. USB was physically
disconnected at the cue. The collector verified V41's exact `/init` hash and
pinned SSH at `192.168.100.4` in 83 successful samples, through phone uptime
207.94. Wi-Fi was ready at uptime 91.71. The parent began health at 191.85;
the child loaded battery and thermal modules, reported zero, created its ready
marker, and showed valid readings around 27.9°C battery and 35–42°C CPU.
The next SSH sample failed, and no later contact appeared. Raw samples and
the checksummed collector receipt are at
`logs/v41-health-window-1792618547838074325/`.

The parent result is **not yet known**. V41's persistent stage file must be
recovered after restoring V33; loss of SSH alone cannot distinguish a deliberate
health-failure power-off from another reset or network loss. Fastboot had not
yet appeared on USB when this note was written. V41 is still the last image
written to `boot_a`; exact V33 rollback is ready. First capture read-only
PL/LK logs if Fastboot becomes available, then restore V33 only to `boot_a`,
reboot unplugged, verify Alpine PID 1, and retrieve the persistent stage file.
Do not start another diagnostic flash before recovery.

The trial procedure is to flash only `boot_a`
after a fresh Fastboot identity/layout check, capture the entire unplugged
boot window, and restore exact V33 to `boot_a` before resuming Alpine. No slot
B, bootloader, recovery, `vendor_boot`, `dtbo`, or `vbmeta` writes.
