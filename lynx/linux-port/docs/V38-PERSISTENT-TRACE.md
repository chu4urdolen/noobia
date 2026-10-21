# V38 persistent boot-stage diagnostic — offline candidate

The V37 trial saw no pinned SSH contact and left no new pstore or expdb
evidence. Its execution boundary remains unknown. V38 asks whether the
diagnostic reaches userspace, starts Wi-Fi, and survives specific uptime
milestones even when the host cannot connect.

V38 derives from the exact V37 image and changes only the primary `/init`
tail. The stock kernel, command line, supplementary payload, AVB footer, and
other ramdisk members are unchanged. It uses the V37 Wi-Fi/SSH startup, does
not start the health modules or Alpine, and requests power-off at uptime 190
seconds. A separate 230-second timer requests power-off if the main path
stalls. It is a bounded diagnostic, **not** a daily boot image.

The new part is a small persistent record on the existing Alpine ext4 root.
Before each write, `/init` checks `userdata` partition name and size, block
node, exact `LYNXROOT` label and UUID, ext4 type, and absence of another
mount. It mounts the filesystem with `nosuid,nodev,noexec`, checks the Alpine
release and relevant paths, appends one boot-ID-scoped checksummed stage line
under `/var/log/lynx-bootdiag/`, syncs that file, and unmounts immediately.
Expected markers are `START`, `WIFI_READY` or `WIFI_FAILED`, uptime 120/150/180,
and `END` or `CHARGER_ON`. A failure to make a required record requests
power-off. These are **real writes to the persistent Alpine filesystem**;
offline validation cannot prove that the mount, write, or unmount is safe on
Lynx. A sudden reset during a write could leave a partial line or require
ext4 journal recovery. The parser rejects malformed or altered records.

Private image:
`linux-port/artifacts/persistent-trace-v38-offline/nord3-persistent-trace-v38-untested.img`.
SHA-256: `ba1176676174bef30d111bff51139f238117f89e416b7fa72c2619f53396b8ad`.
The build and validation receipts are beside it. Validation checked exact
V37 parent, stock kernel, unchanged supplement/AVB, init-only change,
BusyBox syntax, local guard strings, AVB model behavior, and exact V33/V19
rollback images. `tools/lynx_boot_a_v38_trial.py --prepare` passed without
phone contact. The three-second V38 collector dry run against the existing
V33 Alpine boot correctly reported `candidate_seen=false` at
`logs/v38-persistent-window-1792602051750059828/result.json`. The parser's
positive and corruption fixtures are at
`logs/v38-parser-fixture-1792601923902356185/`. A read-only retrieval dry
run on V33 reported no V38 log directory, as expected:
`logs/v38-persistent-capture-1792601966108698756/result.json`.

## Hardware result — complete bounded run; V33 restored

On 2026-10-21, a fresh Fastboot identity/layout preflight passed. The guarded
tool flashed V38 **only to `boot_a`** and rebooted separately with the pinned
collector already running:
`logs/v38-boot-a-trial-1792602285351090717/result.json` and
`logs/v38-boot-a-trial-1792602291789496814/result.json`. No other partition
was flashed. The collector matched V38's exact `/init` hash on boot ID
`5124107b-05e1-49f4-b727-c03d9ec50ec5` and saved 74 complete matching
SSH snapshots from uptime 93.05 through 189.51 seconds. A snapshot begun at
190.89 seconds timed out when the planned shutdown began. The result is at
`logs/v38-persistent-window-1792602238668763311/incident-summary.json`.

After restoring V33, the persistent log was read and its per-line checksums,
boot ID, monotonic uptime, file length, and whole-file hash verified:
`logs/v38-persistent-capture-1792615448786856168/result.json`. It contains
`START` at 8 seconds, `WIFI_READY` at 90, `UPTIME_120`, `UPTIME_150`,
`UPTIME_180`, and `END` at 190. There is no `CHARGER_ON` or `WIFI_FAILED`
marker. The log proves the diagnostic reached userspace and persisted each
stage. It does not by itself prove the electrical power state after the
power-off request; disappearance at that precise boundary is consistent with
the requested shutdown. It also does not prove automatic health or Alpine
handoff, which V38 intentionally omitted.

The first host retrieval attempt failed before reading any file because its
shell filename guard rejected the `.log` suffix. The guard was corrected;
the second retrieval verified the record. This was a host-tool bug, not a
failed phone write.

Lynx later entered Fastboot on USB. A fresh identity/layout check passed,
and exact V33 was restored **only to `boot_a`**, without an implicit reboot:
`logs/v34-boot-a-trial-1792615245603834462/result.json`. A separately
started pinned collector verified V33 rescue SSH, then the RAM health trial,
V33 arm, and independent Alpine PID 1 verifier all passed on boot ID
`948712a7-ea62-4c7e-9f91-e46b33547a2d`:
`logs/v33-alpine-pid1-verification-1792615414672211297/result.json`.
**V33 is installed; Alpine/OpenRC is running.** The boot still requires the
host-assisted health/handoff sequence.

The sustained Wi-Fi-only run through 190 seconds makes automatic health
startup or handoff a better next investigation target than elapsed uptime
alone. It does not establish a root cause for V34–V36 failures.

If a V38 hardware trial is chosen later, first establish Fastboot on USB,
start `tools/capture_v38_persistent_window.py`, and use the guarded
`tools/lynx_boot_a_v38_trial.py` for a fresh Fastboot preflight, `boot_a`-only
flash, and separate reboot. The user must then unplug USB promptly to keep
charging offline. If contact is lost and Lynx returns to Fastboot, capture
the read-only preloader/LK log with `sudo -n python3 tools/lynx_pllk_log.py
--connect` before restoring V33. Restore exact V33 only to `boot_a` with
`sudo -n python3 tools/lynx_boot_a_v34_trial.py --restore-v33`; that tool
performs a new Fastboot preflight and does not reboot. After a verified V33
Alpine boot, read V38 stage logs with
`tools/capture_v38_persistent_trace.py --contact-receipt <fresh-V33-contact>`.
Preserve slot B, bootloader, recovery, and other partitions.
