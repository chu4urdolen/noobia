# Exact-candidate ARM64 boot test

On 2026-10-10, the unchanged compressed stock kernel and initramfs extracted
from `artifacts/busybox-offline/nord3-busybox-candidate.img` booted in QEMU
8.2.2 using its synthetic ARM64 virt board. Candidate SHA-256:
`1db1530625009be376ed45c6731ea97a5ac457e66b703a73621057d542ae6557`.

Observed evidence in `artifacts/emulated-boot/console.log`:

```text
Run /init as init process
noobia-init: NORD3_NATIVE_LINUX_PID1_OK pid=1
noobia-init: Initial sysfs device scan completed
EMULATED_PID1_COMM=init
EMULATED_CPU_ARCH=aarch64
EMULATED_DEVTMPFS_MOUNTS=0
reboot: Power down
```

The native shell executed the three queries, then powered off the virtual
machine. Manual tmpfs device-node setup works for this kernel and userspace.
The final run exited normally in 1.83 seconds. Hashes, command arguments and
limits are recorded in `artifacts/emulated-boot/result.json`. A preceding
120-second run reached the shell but the harness missed BusyBox's `~ #` prompt;
its log/result are preserved in the adjacent `previous-*` directory. Fixing
the harness did not change the candidate.

Run `python3 emulate_first_boot.py` from this workspace to reproduce the test
after preparing the local QEMU dependencies. Downloads, isolated APT indexes,
unpacked packages and package hash manifests live under
`/noobia/lynx/tools/qemu`. No host packages were installed or host APT
sources changed.

The emulator has no guest disk, network interface, monitor or physical USB
passthrough. Its command line deliberately omits `noobia.usb=1`, since the
synthetic board has no MT6983 controller. The stock phone DTB and vendor ramdisk
are not part of this virtual-board test. USB module loading, gadget operation,
display, phone bootloader acceptance and recovery preservation remain unproven.
Lynx was not contacted. No phone partitions were modified, and the image remains
`flash_eligible=false` pending a usable restoration procedure.
