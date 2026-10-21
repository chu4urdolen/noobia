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

## Controlled hardware trial

V40 was flashed to `boot_a` after a fresh Fastboot preflight and rebooted with
the pinned SSH collector already listening. The collector observed no V40
SSH candidate or sample through more than 260 seconds. Fastboot later became
available; a read-only PL/LK dump was saved at
`logs/pllk-1792617274713043558.json`. This is insufficient to locate the
failure: it could have stopped before Wi-Fi, lost networking, or rebooted.
The bootloader dump reports watchdog status but does not by itself identify
the failed kernel stage.

Exact V33 was restored **only to `boot_a`**, with the guarded tool reporting
`v33-restored-no-reboot` at
`logs/v34-boot-a-trial-1792617277371546690/result.json`. A separate Fastboot
reboot was sent, but no pinned V33 SSH contact appeared during the initial
observation. Fastboot reappeared and a second read-only dump was saved at
`logs/pllk-1792617542147639603.json`. A second V33 Fastboot reboot then
reached pinned rescue SSH at `192.168.100.4`. Its V31 RAM health check and
OpenRC/Alpine PID 1 passed:
`logs/v33-alpine-pid1-verification-1792617781090767073/result.json`.
The USB kernel journal confirms actual cable disconnects during both V40
and V33 boot windows.

The read-only persistent capture
`logs/v38-persistent-capture-1792617783351689411/result.json` verified the
old V38 and V39 stage files but found **no V40 file**. Thus V40 never made a
verified first `START` write. Its modified supplementary payload is a plausible
early failure site, but this evidence does not distinguish payload loading,
the stage writer, or an earlier boot failure. The image remains under review.

The image is a bounded diagnostic, not a daily boot image. Do not repeat its
flash without resolving the missing first stage. The established procedure
is to start
`tools/capture_v40_health_window.py` first; then use guarded
`tools/lynx_boot_a_v40_trial.py` for a fresh Fastboot preflight, `boot_a`-only
flash, and separate reboot. Promptly unplug USB. Verify V33 Alpine and
retrieve the boot-ID-scoped stage record with
`tools/capture_v38_persistent_trace.py`. Preserve slot B, bootloader,
recovery, and all other partitions.
