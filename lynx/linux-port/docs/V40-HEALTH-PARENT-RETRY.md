# V40 parent health-check diagnostic — offline candidate

V39 proved Wi-Fi/SSH through uptime 190 and the V31 health child reported
ready, but its parent returned failure at uptime 195 and deliberately
powered off. The recovered checksummed stage file has `HEALTH_BEGIN` and
`HEALTH_FAILED`, without `HEALTH_READY`. Its last SSH sample showed the child
result was zero and its `ready` marker existed. Twelve later read-only runs
of the same supervisor `--once` check passed on a recovered V33 Alpine boot;
that supports, but does not prove, a startup race or transient sample.

V40 derives from exact V39. It changes only the primary `/init` tail,
primary payload length/hash metadata, and the supplementary
`autonomous-health-local-handoff.sh`. The stock kernel, command line,
other ramdisk and payload members, health modules, factory data, and AVB
footer remain unchanged. The health child and its independent safety
watchers are unchanged. The parent now captures the output of its final
read-only supervisor check and retries it at most twice, one second apart,
matching the running supervisor's existing tolerance for three consecutive
bad observations. If it still fails, V40 records a small failure class in
the existing checksummed persistent stage log, requests power-off, and keeps
the independent 420-second outer timer and charger guard. On success it
records `HEALTH_READY`, observes BusyBox with the health supervisor through
uptime 300, and requests power-off. It does **not** hand off to Alpine.

Private image:
`linux-port/artifacts/health-parent-retry-v40-offline/nord3-health-parent-retry-v40-untested.img`,
SHA-256 `5c4a7274e1d6c62183993084e08cc069f704fa9b7fd731e7922567e0bbecfe6f`.
The builder and independent validator receipts are beside it. Validation
checked exact V39 parent, stock kernel, precise primary and supplementary
member scope, BusyBox syntax, exact V33/V19 rollback images, and the pinned
AVB model in locked and unlocked cases. The guarded trial's `--prepare`
passed without phone contact. A read-only collector dry run on current V33
Alpine captured three pinned samples and correctly reported
`candidate_seen=false`:
`logs/v40-health-window-1792616863275965510/result.json`. A reason-code
parser fixture passed at `logs/v40-parser-fixture-1792616877215768486/`.

**V40 has not been flashed or booted.** V33 remains installed, with Alpine
and direct SSH last verified running. Offline checks cannot prove whether
the parent check will pass, whether a health watcher will remain active, or
whether the phone will power off as requested. This is a bounded diagnostic,
not a daily boot image. If trialled, start
`tools/capture_v40_health_window.py` first; then use guarded
`tools/lynx_boot_a_v40_trial.py` for a fresh Fastboot preflight, `boot_a`-only
flash, and separate reboot. Promptly unplug USB. Restore exact V33 only to
`boot_a` after the observation window, then verify V33 Alpine and retrieve
the boot-ID-scoped stage record with
`tools/capture_v38_persistent_trace.py`. Preserve slot B, bootloader,
recovery, and all other partitions.
