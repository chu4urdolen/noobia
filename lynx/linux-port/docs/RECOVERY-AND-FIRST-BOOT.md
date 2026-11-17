# Lynx: native Linux trials and recovery requirements

Device: OnePlus Nord 3 CPH2493, MediaTek MT6983, fastboot product
`k6983v1_64`, serial `89BYAY5L4T9HFUOV`. The phone currently has an unlocked
bootloader and active slot `a`. It already bootloops into Orange State when
starting the installed system. A complete stock-system recovery has not been
tested; the saved CPH2493 A.10 package is a recovery resource, not a proven
recovery guarantee.

## Built candidate

`artifacts/busybox-first-boot/nord3-busybox-ramboot-candidate.img` is a native
Linux development image, not a postmarketOS installation or Android ROM.
It uses the exact stock `5.10.149-android12-9-o-gfec911b5087c` kernel, a static
AArch64 BusyBox, and 24 stock modules forming the selected USB driver dependency
closure. The configuration supports the ingredients needed for native Linux
userspace; actual startup on Lynx has not been demonstrated.

The image uses Android boot header v4 and is 21,590,016 bytes, below the phone's
64 MiB download/boot-image limit. Its custom ramdisk is gzip/newc; the stock
kernel has `CONFIG_BLK_DEV_INITRD=y` and `CONFIG_RD_GZIP=y`. `/init` mounts proc,
sysfs and tmpfs, creates the initial device nodes, runs `mdev -s`, and keeps PID 1
alive even if an interactive shell exits. Device nodes for console and null are
also present in the archive for the kernel's initial console setup.

Offline checks completed: repository/payload checksums for BusyBox, static ELF
and AArch64 architecture checks, native execution of the BusyBox applet listing
on Argus, target BusyBox shell-syntax validation, unchanged stock kernel bytes,
module dependency closure, size limit, and independent AOSP boot-image parsing.
The BusyBox publisher signature has not been cryptographically verified; its
package was obtained from Alpine's official HTTPS repository. The modified
boot image does not retain a valid OEM/GKI signature and is not for relocking.

## Preservation boundary

Only a temporary `fastboot boot` trial is contemplated. No `flash`, `erase`,
`format`, `set_active`, bootloader lock/unlock, recovery replacement, or MediaTek
download-agent/preloader operation belongs in this first trial. The initramfs
does not mount block devices or write to storage partitions. USB-related
hardware drivers initialize the normal controller hardware.

Header v4 normally obtains the DTB and vendor ramdisk from the installed
`vendor_boot` and overlays from `dtbo`. The current on-device versions have not
been read back; the extracted stock DTB and DTBO are retained locally. Their
interaction with the temporary boot image is a hardware-test uncertainty.
Fastboot RAM boot was rejected in the observed trial. An unsupported or rejected
RAM-boot command must stop the attempt, with no flash-based fallback.

## Trial and success criteria

The historical trial command was (do not repeat as a fallback to flashing):

```sh
/noobia/lynx/tools/platform-tools/fastboot \
  -s 89BYAY5L4T9HFUOV boot \
  /noobia/lynx/linux-port/artifacts/busybox-first-boot/nord3-busybox-ramboot-candidate.img
```

Success requires observing `NORD3_NATIVE_LINUX_PID1_OK` from the diagnostic
console, then confirming `uname -a` and `/proc/1/comm`. A successful Fastboot
download, a logo, or a USB enumeration alone is not proof of a Linux boot.

The USB gadget requests CDC ACM serial plus CDC ECM Ethernet. A working serial
interface should appear as a new `/dev/ttyACM*` on Nexus. USB Ethernet uses
device address `172.16.42.1/30`; any host address configuration must apply only
to the newly identified USB interface. There is no SSH server in this first
BusyBox image. Display, touch, Wi-Fi, modem, audio and thermal userspace are not
part of this first milestone.

## Return to Fastboot

The user already demonstrated that Power + Volume Down enters the phone's
Fastboot Mode. Use that demonstrated combination through a restart if the
temporary image hangs or the installed system resumes its previous loop.
The candidate includes `panic=10`, so a kernel panic should reboot rather than
leave the handset indefinitely stuck. A reset discards a temporary RAM image.

Once Fastboot returns, recheck `product`, `unlocked`, and `current-slot`. The
expected values remain `k6983v1_64`, `yes`, and `a`. Stop if Fastboot cannot be
recovered; do not try preloader flashing or partition erasure.

## Later postmarketOS work

The saved stock configuration disables `CONFIG_DEVTMPFS`; the official
postmarketOS initramfs currently explicitly mounts devtmpfs. A proper port
should eventually enable `CONFIG_DEVTMPFS=y` and `CONFIG_DEVTMPFS_MOUNT=y`
and still explicitly mount devtmpfs in the initramfs. Rebuilding must account
for the stock module ABI and `CONFIG_MODVERSIONS=y`; matching version strings
alone are insufficient proof that rebuilt kernels accept existing modules.

The inspected pmaports commit is
`2beaeebfe21562c60bcdd122114b05baaf34d765`. No `vitamin` or `mt6983` device path
was found in that checkout. Other OnePlus ports supply packaging references,
not compatible hardware binaries.

Sources:
- https://www.kernel.org/doc/html/latest/filesystems/ramfs-rootfs-initramfs.html
- https://github.com/OnePlusOSS/android_kernel_5.10_oneplus_mt6983
- https://github.com/OnePlusOSS/android_kernel_modules_oneplus_mt6983
- https://github.com/lineageos-on-vitamin/android_device_oneplus_vitamin
- https://gitlab.com/Mashopy/proprietary_vendor_oneplus_vitamin
- https://gitlab.postmarketos.org/postmarketOS/pmaports
- https://android.googlesource.com/platform/system/tools/mkbootimg

## Observed trial results, 2026-10-10

The phone accepted the complete 21,590,016-byte download into RAM, then rejected
`fastboot boot` with `FAILED (remote: 'unknown command')`. The native kernel was
not started by that attempt. Subsequent queries returned the same product,
unlocked state and active slot `a`. No partition was flashed or erased.

A read-only `fastboot fetch vendor_boot_a` attempt also failed: the bootloader
does not implement `max-fetch-size`/fetch support. No original partition backup
was produced.

`fastboot reboot recovery` was accepted, but the user observed the original
Orange State restart loop rather than a working recovery menu. The user is
returning the handset to its demonstrated Fastboot Mode. A reliable recovery
and boot-partition backup route must be established before a storage-based test
of this candidate. The present build is not approved for flashing.

The user subsequently reached a recovery menu with Format data, Reboot device,
and Power off. Selecting Power off, then entering Fastboot physically, restored
USB Fastboot access; product, unlock state and active slot were rechecked and
unchanged. Recovery has an observed physical entry path, but the software
recovery reboot remains unreliable: a second requested ADB inspection again
produced the Orange State loop and no USB/ADB device. No shell access has yet
been established in the actual recovery menu.

The extracted package is `CPH2493_13.1.0.543(EX01)_230707`. Its model/platform
match, but its build has not been matched to the firmware installed on the
phone. These package components must not be described as original partition
backups. See `stock-component-manifest.json` for sizes and SHA-256 hashes.

The user then confirmed that the recovery menu was open and USB connected.
With that actual recovery state confirmed, `lsusb` showed no phone, the kernel
log showed no recent phone USB enumeration, `adb devices -l` was empty, and
`adb -s 89BYAY5L4T9HFUOV shell id` returned device not found. The three-option
stock recovery screen therefore currently provides no USB/ADB access; its shell
could not be used to read boot_a, vendor_boot_a, dtbo_a or vbmeta_a. No partition
modification was performed. Any other recovery interface remains untested.

`fastboot reboot fastboot` was subsequently accepted but returned the Orange
State loop; fastbootd was not observed. Lynx was powered off. Current work is
offline and does not require entering another phone mode.

## Recovery boundary audit

`audit_recovery_boundary.py` inspects the stock and candidate ramdisks without
running their contents. The stock generic ramdisk contains a 3,143,528-byte
`init` executable. The vendor ramdisk contains an `init` symlink to
`/system/bin/init`, a separate init executable there, recovery executables,
recovery fstab, and a recovery module list. The Linux candidate substitutes its
own `/init`; the 24 overlapping USB modules are byte-identical to this package.

AOSP documents that the generic ramdisk overlays the vendor ramdisk:
https://source.android.com/docs/core/architecture/partitions/vendor-boot-partitions
Therefore retaining vendor_boot does not by itself prove that stock recovery
will still start. A future recovery dispatcher needs the actual recovery boot
signal and a validated stock init handoff; guessing from another handset would
not satisfy the preservation requirement. The audit is against a reference
package, not a readback from Lynx. See `recovery-boundary-audit.json`.
