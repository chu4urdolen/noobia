# V42 post-readiness trace — offline candidate

V41's checksum-verified stage records show four boots reached `HEALTH_READY`
at uptime 196–208, but none recorded the intended `END` at 300. Pinned SSH
for the observed boot ended just after its `HEALTH_READY` marker. The V41
observation loop requests power-off on one failed supervisor `--once` sample
but leaves no persistent marker on that path. The stop remains unclassified.

V42 derives from the exact V41 image. Its only logical change replaces that
post-readiness failure log line with the existing checksummed
`HEALTH_FAIL_POSTCHECK` stage append. It keeps the stock kernel, command line,
V41 health startup and safety timers, and the **entire V39 supplementary
payload unchanged**. It does not hand off to Alpine. A V42 trial can now
distinguish a failed observation check from another stop if the persistent
stage writer remains available.

Private image:
`artifacts/health-observe-v42-offline/nord3-health-observe-v42-untested.img`,
SHA-256 `c7cb6b3a4a1619eb04bdc7a573eca7eb70644ea23d67028f8b5fa45ba8a7ce8e`.
The builder and independent validator receipts are beside it. Validation
proved the exact single-line `/init` delta, BusyBox syntax, unchanged
supplement, stock kernel, V33/V19 rollback hashes, and pinned AVB model in
unlocked and locked cases. The guarded `--prepare` check passed. A one-second
pinned collector dry run against live V33 captured one sample and correctly
reported `candidate_seen=false` at
`logs/v42-health-window-1792659683224771990/result.json`.

## Controlled hardware trial — cause isolated; V33 recovered

After fresh Fastboot preflight, V42 was flashed **only to `boot_a`** and
rebooted with the pinned collector already listening. The Nexus USB journal
confirmed disconnection at the cue. The collector verified exact V42 `/init`
and pinned Wi-Fi SSH at `192.168.100.6` in 90 successful samples, through
phone uptime 210.33. The health child had reported zero and created its ready
marker. The next SSH sample failed; no contact returned by collector elapsed
299 seconds. Raw samples and receipt:
`logs/v42-health-window-1792660627066082992/`.

After Fastboot returned, a read-only PL/LK log was saved at
`logs/pllk-1792667178003560818.json`. Exact V33 was restored **only to
`boot_a`** at `logs/v34-boot-a-trial-1792667181150978382/result.json`.
Its first reboot did not reach SSH; Fastboot returned and another read-only
log was saved at `logs/pllk-1792667478825311987.json`. A second V33 reboot
reached pinned SSH. V31 RAM health and Alpine/OpenRC PID 1 passed:
`logs/v33-alpine-pid1-verification-1792667635515102275/result.json`.

The checksum-verified persistent capture
`logs/v38-persistent-capture-1792667638510281486/result.json` contains three
V42 boot IDs. All reached `HEALTH_READY` at uptime 209–211 and then recorded
`HEALTH_FAIL_POSTCHECK` at uptime 210–211. The observed boot ID
`1bf54de5-08d4-44b7-9878-fde4acef277b` recorded both at uptime 211.
This **confirms the immediate post-readiness supervisor `--once` check** is
what requests power-off. It does not identify which inner supervisor condition
failed. That check is stricter than the independent supervisor's existing
three-consecutive-failures policy; the parent should use comparable tolerance
or rely on the independently running supervisor, with its death detected.

V33 is installed and Alpine was last verified running. Do not repeat V42.

The established hardware procedure uses
`tools/capture_v42_health_window.py` before the guarded
`tools/lynx_boot_a_v42_trial.py` flash of `boot_a` only, followed by a
separate reboot and prompt USB unplug. Capture read-only PL/LK if contact
ends unexpectedly, restore exact V33 only to `boot_a`, verify Alpine, then
read the checksummed stage file. Preserve slot B, bootloader, recovery, and
all other partitions.
