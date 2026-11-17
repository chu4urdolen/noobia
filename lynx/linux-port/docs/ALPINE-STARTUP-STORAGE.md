# Alpine startup, live diagnostics and storage

Three separate results now establish the next Linux foundation:

- On Lynx, Alpine's RAM chroot can inspect the live kernel through read-only
  proc and sysfs mounts. Its `free`, `ps` and `strace` work on real phone data.
- In an isolated VM, the signed Alpine mini-rootfs boots its own shell as
  PID 1 on the exact stock kernel, without an outer static BusyBox or chroot.
- A read-only live storage capture maps 86 UFS partitions and confirms that
  installed `boot_a` has the exact frozen V19 image hash.

The VM startup has not been installed on Lynx. Her original BusyBox PID 1,
Wi-Fi, SSH and temperature watchers continue on the same boot. No partition
was written or mounted, and no kernel module was added during this work.

## Live read-only diagnostics

`linux-port/alpine-observability.sh --apply BOOT_ID`, run outside the chroot,
checks the current boot identity and Alpine release, refuses symlink targets,
and mounts proc and sysfs at the existing RAM rootfs's `proc` and `sys`
directories. It requires `ro,nosuid,nodev,noexec` and verifies the original
outer `/proc` and `/sys` mount entries remain unchanged. An existing compatible
mount is adopted; an incompatible mount causes refusal. `--status BOOT_ID`
checks without creating mounts. Partial failures leave evidence and any
already-created mounts in place. No mount or service is restarted.

Use the existing host wrapper from `/noobia/lynx`:

```sh
tools/lynx-alpine free -m
tools/lynx-alpine ps w
tools/lynx-alpine cat /sys/class/net/wlan0/operstate
```

These commands are bounded, logged and tied to the current verified RAM
rootfs and boot. The mounts expose the shared process namespace and kernel;
this chroot is not a security isolation boundary. No block nodes or outer
`/dev` bind mount were added. Root privileges in the outer environment remain
capable of changing mount permissions; these flags prevent accidental writes
through these particular mounts, not all possible privileged operations.

The first live probe incorrectly expected outer mount paths inside the
chroot's `/proc/mounts` and stopped at its grep check. Paths there are relative
to the chroot. Correcting the check to `/proc` and `/sys` passed, followed by
real traced `O_RDONLY` opens of `/proc/meminfo` and the Wi-Fi operstate file.
The failed probe is retained; the mounts did not need changing.

## Direct Alpine PID 1 VM test

```sh
python3 tools/test_alpine_pid1_kernel.py --rootfs-receipt ROOTFS_RECEIPT
```

The harness validates the signed, pinned Alpine archive and frozen V19 image,
uses the unchanged stock kernel, and packs Alpine at the initramfs root. Its
`/init` interpreter is Alpine's dynamically linked `/bin/sh`. The script
requires PID 1, `/proc/1/exe` pointing at `/bin/busybox`, and a matching SHA256
of that executable from the signed archive. No outer helper runs the probe.

It manually mounts proc/sysfs and tmpfs `/dev`, creates basic device nodes,
mounts devpts and a bounded RAM `/run`, runs the shell/musl/APK probe, checks a
RAM write and sysfs CPU visibility, then powers off. The VM has no NIC, disk
or handset connection. Successful run elapsed about four seconds. Console,
init source, input inventory and hashes are preserved. Timeout is 55 seconds.

This tests an Alpine shell as PID 1, not OpenRC. It does not test handset
driver startup, Android boot image packaging, persistent storage, display or
the phone's recovery path. The VM's `initramfs` is not a flashable phone boot
image. No image in this experiment is selected for a hardware trial.

## Read-only storage map

`tools/audit_partition_map.py --receipt CAPTURE_RECEIPT` validates the durable
native capture offline. It checks its hash and native proof, partition labels
and device numbers, bounds, alignment and overlaps. Seven corrupted-input
checks confirmed rejection of incomplete captures, wrong boot hash, zero
size, overlap, duplicate labels, mismatched devices and invalid geometry.

Observed main UFS device is `sdc`, 255,919,652,864 bytes. Its logical and
physical blocks are 4096 bytes; sysfs `start` and `size` use 512-byte sectors.
This is the live device's observed geometry, not the original purchase
description. The map retains exact starts and sizes for all 86 partitions.

| Label | Device | Size |
| --- | --- | --- |
| boot_a | sdc39 | 64 MiB |
| vendor_boot_a | sdc40 | 64 MiB |
| init_boot_a | sdc41 | 8 MiB |
| dtbo_a | sdc42 | 8 MiB |
| userdata | sdc85 | See full private map |

Read-only SHA256 of `/dev/sdc39` is
`5ce2dbf8a7c132fa7e31f6be70aa76f83afe8c293e2cd5f02251a532486fd851`,
matching V19 byte for byte. This corroborates the currently installed boot
image, not the integrity of every other partition. The map is kernel sysfs
evidence, not an independent verification of GPT CRCs.

The kernel lists ext4, F2FS and EROFS filesystem support. A bounded read of
the first 4096 bytes of `userdata` found neither the ext4 nor F2FS magic at
their normal first-superblock offsets; it was not all zero. This does not
prove encryption, emptiness or corruption. No filesystem repair, mount,
format or partition change followed. Persistent rootfs placement remains an
unresolved step; this partition must not be treated as an empty destination.

## Next hardware integration boundary

The new VM init deliberately omits phone-specific module and Wi-Fi startup.
A handset candidate must retain the proven V19 early boot and dependency
order, SSH access and current battery/thermal protections before changing
which userspace supervises services. The existing RAM tools already support
useful work while that integration is prepared offline. The Linux flash hold,
working image, stock undo and slot B remain unchanged.

## Private evidence

- System inventory: `logs/live-system-storage-inventory-1792181341591807206`.
- Partition map/hash: `logs/live-partition-map-1792181379560943113`, including
  `partition-map-analysis.json`.
- Map rejection checks: `logs/partition-map-negative-check-1792181517015425625.json`.
- Direct Alpine PID 1 VM: `linux-port/artifacts/emulated-alpine-pid1-1792181417394955482`.
- Read-only mount installation: `logs/live-alpine-readonly-observability-1792181496340538362`.
- Failed/successful live chroot probes: `logs/live-alpine-cli-1792181517068390838`
  and `logs/live-alpine-cli-1792181526852271892`.
- Mount status: `logs/live-alpine-readonly-observability-status-1792181528516466130`.
- Power runtime postcheck: `logs/runtime-power-setup-1792181527526386651`.
- Bounded userdata read: `logs/live-userdata-header-1792181546190048618`.

All raw storage captures, input binaries and VM artifacts remain private.
