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
