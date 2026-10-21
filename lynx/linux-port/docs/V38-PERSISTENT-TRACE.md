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

**V38 has not been flashed or booted.** V33 remains the installed `boot_a`
image, and Alpine/OpenRC plus direct pinned SSH are last verified running.
There is no user action needed for offline preparation.

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
