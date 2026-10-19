# Lynx persistent storage: read-only survey

On the V19 boot authenticated at
`logs/wifi-v19-contact-1792349585406385976/result.json`, the automatic health
stage passed at `logs/autonomous-health-ram-trial-1792350300055886410/result.json`.
The verified Alpine 3.24.2 checkpoint was restored into `/run` RAM after a
missing `/dev` directory was repaired. Python 3.14.8, Git 2.54.0 and Make 4.4.1
run natively; see `logs/alpine-checkpoint-live-repair-1792350451274224367/result.json`.
This is still BusyBox PID 1 with an Alpine chroot, not persistent Alpine boot.

Read-only UFS inspection found `userdata` at `/dev/sdc85`, 466,026,432
512-byte sectors (238,605,533,184 bytes). Fastboot describes it as `f2fs`,
but it is not mounted and a read-only signature probe found neither the F2FS
magic at byte 1024 nor the ext4 magic at byte 1080. BusyBox `blkid` reported no
filesystem. The kernel supports both ext4 and F2FS. No filesystem was mounted,
formatted, repaired or written in this survey.

The missing signature does not prove the partition is empty; encryption or a
damaged/offset filesystem could hide contents. Before reusing `userdata`, save
its partition table and a bounded forensic header, confirm the stock OTA can
restore the boot chain, and prepare a clear destructive-storage decision. The
working V19 and exact stock `boot_a` images remain separate on Nexus. A Linux
rootfs on `userdata` cannot be assumed ready merely because Fastboot labels it
F2FS.

A full sysfs partition-name/size inventory is preserved at
`logs/ufs-layout-readonly-1792350847180380464/result.json`. The only large
general-purpose candidates are `super` (15,032,385,536 bytes) and `userdata`
(238,605,533,184 bytes). The other partitions at or above 128 MiB are modem,
OPLUS reserve and crash-log regions; they are not suitable scratch space.
Reusing `super` could remove stock vendor components and complicate recovery.
No partition was modified to reach this conclusion.

On October 19, the same authenticated V19 boot remained alive despite a
temporary SSH refusal. Its boot ID was
`32dd2438-fbac-4693-8023-d0dcc7c74771`; Alpine 3.24.2 still ran in RAM,
and the health supervisor continued to report valid samples. The previous
network loss must not be described as a confirmed power-off or failed Alpine
restore.

`tools/backup_userdata_edges.py` then read, without mounting or writing the
phone partition, the first and last 16 MiB of `userdata` into the restricted
Nexus directory `backups/userdata-edges-1792413021056852842/`. The manifest
records the phone boot ID, exact offsets and SHA-256 hashes. Both local files
were independently hashed after transfer. The final 16 MiB are entirely zero;
the first 16 MiB contain nonzero data but no recognized filesystem signature.
This bounded backup is **not** a full backup of the 238.6 GB partition and
does not authorize formatting. The separate sysfs partition inventory remains
the partition-layout record; only these two `userdata` regions were copied.
