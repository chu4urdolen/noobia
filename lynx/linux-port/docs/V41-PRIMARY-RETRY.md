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

## Controlled hardware trial — V33 recovered

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

After Fastboot returned, the read-only PL/LK log was saved at
`logs/pllk-1792659321026068338.json`. Exact V33 was restored **only to
`boot_a`** at `logs/v34-boot-a-trial-1792659331772439906/result.json`, then
rebooted unplugged. Pinned SSH, V31 RAM health, and Alpine/OpenRC PID 1 passed:
`logs/v33-alpine-pid1-verification-1792659494972296336/result.json`.

The recovered, checksum-verified persistent capture is
`logs/v38-persistent-capture-1792659498990866325/result.json`. It found four
V41 boot IDs, each reaching `HEALTH_READY` at uptime 196–208. The observed
boot ID `0ee541c6-8c18-4a7b-84cd-a6713d7a4e04` recorded `HEALTH_READY`
at uptime 208, immediately after the last successful SSH sample at 207.94.
None of the four V41 records contains `END` at uptime 300. This proves the
parent health startup reached success in these boots, but does not prove that
the retry branch was needed. It narrows the lost-contact problem to the
post-readiness observation window or its final stage writer; the exact stop
is still unknown. V41's post-readiness loop requests power-off immediately if
one supervisor `--once` sample fails, without a persistent failure marker.
That path is a plausible explanation, not yet a verified cause.

V33 is installed and Alpine was last verified running. Do not repeat V41;
instrument the post-readiness path before another diagnostic flash.

The trial procedure is to flash only `boot_a`
after a fresh Fastboot identity/layout check, capture the entire unplugged
boot window, and restore exact V33 to `boot_a` before resuming Alpine. No slot
B, bootloader, recovery, `vendor_boot`, `dtbo`, or `vbmeta` writes.
