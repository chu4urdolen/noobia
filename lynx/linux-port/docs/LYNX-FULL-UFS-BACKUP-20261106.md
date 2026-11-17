# Lynx read-only UFS backup, 2026-11-06

Lynx V53 is reachable at `192.168.100.107:2222` with pinned SSH. The host
receiver is `lynx/tools/backup_full_ufs.py`. It only issues remote reads of
`/dev/sda`, `/dev/sdb`, and `/dev/sdc`; its output is restricted to
`/noobia/lynx/backups`. Each gzip chunk is checked against the exact expected
raw length and SHA-256, reopened and decompressed locally, then published with
a JSON receipt. A later run verifies completed chunks before resuming.

The backup directory is
`/noobia/lynx/backups/full-ufs-20261106-v53/`. The two 4 MiB UFS LUNs are
complete. The main 255,919,652,864-byte LUN was being read in 1 GiB chunks by
the user service `lynx-ufs-full-backup.service`. The service checks Lynx's boot
ID, health, battery and temperature before each chunk. It stops below 30%
battery, at 40 °C battery temperature, or if the boot or health changes. It
does not restart automatically after a Nexus reboot. A `.gz.part` after an
interruption must be reviewed and removed before resuming; final files are
never overwritten.

Check progress with:

```sh
systemctl --user status lynx-ufs-full-backup.service
journalctl --user -u lynx-ufs-full-backup.service -n 20 --no-pager
```

At 20:29 EET, Lynx stopped answering SSH during the read-only backup. The
service failed and stayed stopped; the presence monitor also lost Wi-Fi and
Bluetooth. Its last completed chunk was `sdc-023622320128`, covering bytes
23,622,320,128 through 24,696,061,951. There is no partial chunk. The host
audit at about 20:41 verified all **25 saved chunks** (23 GiB of `sdc` plus
both 4 MiB LUNs), totaling **24,704,450,560 raw bytes**, with no errors or
gaps. Lynx's last health check before the loss showed the same V53 boot,
roughly 50% battery and no issues. Do not assume the phone powered off or that
the backup itself caused the disappearance; inspect its screen and, if it
returns, its boot ID and pstore before resuming. No phone partitions were
changed by this backup.

At the later offline check, Lynx remained absent from Wi-Fi and USB.
Dushich's plan-aware auditor was reviewed and corrected in his isolated
workspace (commit `1af72ba`); its 13 tests pass. It decompressed and checked
all saved chunks, reporting `sda` and `sdb` complete, `sdc` at
24,696,061,952/255,919,652,864 bytes (9.6%, valid partial), with no errors.
The phone backup remains stopped until Lynx's screen and boot state are known.

On 2026-11-07, Noob observed Lynx in Fastboot. Nexus confirmed the USB
Fastboot device, `current-slot: a`, `slot-unbootable:a: no`, and
`slot-successful:a: yes`. A single `fastboot reboot` of the unchanged V53
image did not return rescue or Alpine SSH within 90 seconds; Noob then saw
Fastboot again and Nexus confirmed it on USB. Fastboot exposed no usable
battery value or crash reason. This is consistent with the previously observed
V52/V53 warm-boot failure, but does not establish whether the original 20:29
loss was caused by the storage read, a kernel fault, power, or another event.
No partition was written during this diagnostic; the backup remains stopped.

After a physical cold start on 2026-11-07, V53 reached Alpine, Wi-Fi, and SSH
with boot ID `ffe89996-fe1a-4b03-8419-07c49bd0c33f`. Battery health was
57%, 25.1 °C, with no reported issues. Persistent `/var/log/lynx/messages`
identifies the immediate 2026-11-06 20:29 EET event: maintenance logged
`SAFETY_GUARD_FAILED` twice (20:28:36 and 20:29:06), then
`SAFE_POWEROFF reason=safety_guard_failed`. The final battery-history sample
at 20:28:12 was 48%, 25.6 °C, 7708 mV, so a low-capacity cutoff does not
explain this power-off. The log does not identify whether the failing status
probe was `lynx-health` or `lynx-battery-reserve`, nor why it failed.
`/sys/fs/pstore/console-ramoops-0` contains the known older `v4l2-ctl`
camera ioctl Oops at uptime 5157 seconds; it is not evidence of a new
backup-time kernel crash. The pstore and persistent log extracts were saved
under `lynx/logs/boot-investigation-20261107/`.

The maintenance power-off rule was left intact. Its script now logs which
service status failed, plus one-shot health and reserve checks, before applying
the same two-failure threshold. The old script is saved on Lynx at
`/root/lynx-rescue/lynx-maintenance-before-safety-probe-20261107.sh`.
The guarded install receipt is under
`lynx/logs/maintenance-safety-probe-1794004268889423855/`; all safety and
Alpine services passed afterward.

The backup receiver gained an explicit `--resume-after-reboot` option. It
checks Lynx's hardware serial, `/dev/sdc` geometry, and exact V53 `boot_a`
SHA-256, then records the new boot ID in `sdc-resume-events.jsonl` before
rechecking completed chunks. A two-chunk continuation passed, with 25 GiB of
the main LUN now verified. The remaining read-only backup was started as the
transient Nexus user service `lynx-ufs-full-backup.service` with a 40% battery
floor and no automatic restart. This multi-boot raw read is still not a
consistent filesystem snapshot; keep the separate Alpine file-level backup
plan before using it for restoration.

The receiver's gzip verifier now caps each decompressed block at 1 MiB.
Rechecking one sparse and one populated 1 GiB chunk passed with about 25 MiB
peak host RSS each; this avoids the former multi-GiB peak when a 1 MiB gzip
block expands to almost a full sparse chunk. The running systemd service was
launched before that host-side change and will use it only on a future run.
`lynx/tools/backup_alpine_files.py` is prepared for a separate, private
file-level archive after the raw reader stops; its preflight correctly refused
to run while the raw backup service is active.
Dushich built a read-only archive receipt validator in his separate workspace
(commit `bee7e13`, five tests passed). After reviewing it, Aria adopted it as
`lynx/tools/validate_alpine_backup.py`, required all receipt fields and exact
archive roots, and added path-traversal, missing-field, and extra-root tests.
Seven adopted validator tests pass. The file backup now runs that validator
before publishing the archive and receipt.

At 00:41 EET on 2026-11-07, the resumed raw read exposed a reproducible
short-lived health-status failure: the CPU/SoC maximum reached 47.1 °C while
cooling states were still 0. The five-second health-supervisor log also
recorded `cooling not applied` at 45.1 °C and 48.9 °C, each followed by healthy
samples. Aria sent SIGINT to the host backup service, which stopped cleanly
without a `.part` file; Lynx stayed online and returned to normal temperature.
This supports a cooling-sample timing race as a plausible cause of the earlier
maintenance shutdown, though the old log lacks the per-guard detail needed to
prove it was the same fault.

The maintenance rule now defers only this specific transition below 55 °C,
and only when the independent health-supervisor PID is alive and its event log
is recent and contains a healthy sample. A reserve failure, dead watcher,
stale log, other sensor fault, or temperature at or above 55 °C still fails
the maintenance check. Six isolated tests exercise these cases. The new
guarded install receipt is under
`lynx/logs/maintenance-safety-probe-1794005357176317361/`, with the previous
script saved at
`/root/lynx-rescue/lynx-maintenance-before-cooling-grace-v2-20261107.sh`.
The bounded ten-chunk read-only trial completed with a 45% battery floor,
about 29 MiB peak host memory, and Lynx healthy at 54% battery. Its health
supervisor saw brief cooling-sample misses at 50.8 °C and 47.7 °C, each
followed by healthy samples; maintenance did not power off the phone.
The remaining verified read was then started as
`lynx-ufs-final-backup.service`, with no automatic restart and a 45% battery
floor. The host reader checks the completed chunks again before proceeding.
`lynx-backup-finisher.service` waits for that reader. It checks that every
main-LUN chunk and receipt is present, then creates the separate Alpine file
archive only if Lynx is healthy and still has at least 47% battery. It writes
its outcome to `lynx/logs/backup-finish-20261107.json` and does not restart
either job after a Nexus reboot. Neither host service writes to Lynx.

**Scope correction, 2026-11-07:** Noob clarified that a full-device storage
backup was not requested. Aria stopped both the raw reader and the automatic
file-archive finisher. Both services are inactive; no partial chunk remains,
and no file archive was started. The existing 705 MiB of host-side raw chunks
is retained pending a separate cleanup decision. Lynx remained healthy and
online at 50% battery after the stop. Do not resume the full-UFS job or launch
the finisher without a new explicit request. Filesystem growth, if wanted,
needs a small backup of the actual Alpine files and a reviewed resize plan;
the 222 GiB partition itself already exists and needs no repartitioning.

**Restoration limit:** `/dev/sdc85` contains the mounted Alpine ext4 root
inside `/dev/sdc`. This is a live raw read, so a complete LUN image is not a
guaranteed consistent filesystem snapshot. Keep the separate working V53 and
V50 boot images and stock recovery package. Before relying on the raw backup
for restoration, verify all chunk receipts and take a separate file-level
backup of Alpine when the main LUN read has finished or paused. Never write
the raw image back without an explicit restoration plan and device identity
check.
