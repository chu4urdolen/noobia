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

**V42 has not been flashed or booted.** V33 is installed, and Alpine/OpenRC
PID 1 was last verified running unplugged. A hardware trial would use
`tools/capture_v42_health_window.py` before the guarded
`tools/lynx_boot_a_v42_trial.py` flash of `boot_a` only, followed by a
separate reboot and prompt USB unplug. Capture read-only PL/LK if contact
ends unexpectedly, restore exact V33 only to `boot_a`, verify Alpine, then
read the checksummed stage file. Preserve slot B, bootloader, recovery, and
all other partitions.
