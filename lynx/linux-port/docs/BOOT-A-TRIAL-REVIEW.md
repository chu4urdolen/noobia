# Lynx boot_a-only trial — proposed, not executed

## Fresh read-only preflight

Report: `/noobia/lynx/logs/fastboot-preflight-1791602958363822313.json`.
Serial `89BYAY5L4T9HFUOV`, product `k6983v1_64`, unlocked=yes, secure=no,
current-slot=a. Bootloader `k6983v1_64_45ca337_202308100614` matches the August
reference build string. Boot and vendor_boot are each 64 MiB; dtbo and vbmeta
are each 8 MiB. Maximum Fastboot download is 64 MiB. Slot A records successful
yes, unbootable no, retries 7; these flags do not establish a working OS.

USB was stable for all thirteen queries. Initial host access timed out; after
a per-device ACL on `/dev/bus/usb/001/026`, the complete query set succeeded.
No phone partition write, reboot or slot change was issued.

## Proposed change and verified files

Change only `boot_a` to the native BusyBox candidate:
`artifacts/busybox-August/nord3-busybox-candidate.img`, 21,594,112 bytes,
SHA-256 `74bcda633bf85b2601629966e09e68e154863232f6493829b975bb277b3cf7f9`.
It contains the exact August stock kernel and 24 matching USB modules. Native
PID 1, aarch64 shell operation and manual /dev startup passed ARM emulation.
Display and physical USB operation remain untested.

Undo resource for this proposed changed partition:
`artifacts/stock-cph2493-August-eu-ota/boot.img`, 67,108,864 bytes,
SHA-256 `a67f03d7b826b834c23653b67eaa6efa971eb70ef8af19eee4d33fb5fc7fe995`.
Its payload hash and AVB signature were checked. The source OTA passed all ZIP
CRCs, payload FILE_HASH and metadata/full-payload signatures against its included
certificate. This file is a matching-build reference, not a phone readback.

## What remains uncertain

Actual installed vendor_boot and DTBO have not been read back. A matching LK
build does not prove those partitions match the package. A custom generic init
may prevent the current stock recovery menu from starting while it is installed.
Fastboot partition writes and physical restoration have not been tested here.
Thus this would be a controlled hardware experiment with a prepared reference
undo resource, not a previously verified restoration route.

Physical entry into bootloader Fastboot has been demonstrated. The proposed
write does not alter LK, preloader or GPT. The intended repair route is return
to that bootloader and rewrite only boot_a with the checked stock boot image.
This is expected to remove the custom init but cannot guarantee recovery startup
or Android boot. Android is assumed gone; restoring Android first is unnecessary.

The earlier requirement for a verified restoration route has not been met by
a physical restoration test. Proceeding would require explicit acceptance of
this remaining uncertainty, as well as revocation of the latest no-flash limit.
No authorization is inferred from permission to run the read-only preflight.

## Conditional commands for review only

The fixed tool/serial and partition names below are shown to make the proposed
scope concrete. They have NOT been run, and this document is not a flash script.

Trial write, only after explicit authorization and rechecking the file hash:

```sh
/noobia/lynx/tools/platform-tools/fastboot -s 89BYAY5L4T9HFUOV flash boot_a /noobia/lynx/linux-port/artifacts/busybox-August/nord3-busybox-candidate.img
```

If that command fails, stop; no automatic erase or extra partition operation.
If it succeeds, reboot once for an observed short USB-console test. Success
requires the native PID 1 marker and shell confirmation, not a logo or black
screen. Exiting a diagnostic shell leaves native PID 1 running.

If startup fails, use the demonstrated physical Fastboot entry, recheck identity
and slot A, then restore the changed partition using its stock reference:

```sh
/noobia/lynx/tools/platform-tools/fastboot -s 89BYAY5L4T9HFUOV flash boot_a /noobia/lynx/linux-port/artifacts/stock-cph2493-August-eu-ota/boot.img
```

Leave slot B, vendor_boot, dtbo, vbmeta, LK, preloader, GPT, super and userdata
untouched throughout this proposal. Do not add verification-disable, relock,
format-data, both-slot or extra flash commands as fallbacks. If physical Fastboot
cannot be reached, stop and reassess; the previous MTK readback/authentication
attempts did not establish a usable alternative repair route.
