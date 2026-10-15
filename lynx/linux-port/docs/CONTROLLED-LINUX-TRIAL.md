# Lynx: controlled native Linux trial preparation

Android is assumed unusable. Restoring Android first is not a prerequisite.
Native Linux remains the runtime objective. Stock firmware is retained for
restoration and diagnostics, not as the intended installed operating system.

## Slot A observations

Fresh read-only Fastboot queries on 2026-10-10 returned:

```
slot-successful:a: yes
slot-unbootable:a: no
slot-retry-count:a: 7
```

These flags describe recorded bootloader state, not a currently working OS.
Slot B is unverified and must remain untouched. Do not rely on it as a fallback.

## Image prepared

`artifacts/busybox-offline/nord3-busybox-candidate.img` is 21,590,016 bytes.
SHA-256: `1db1530625009be376ed45c6731ea97a5ac457e66b703a73621057d542ae6557`.
It reuses the stock kernel and 24 matching USB modules, with static ARM64
BusyBox, manual device nodes, USB serial and an Ethernet attempt. Essential
mount failures keep PID 1 alive; the serial console includes kernel diagnostics.
ARM64 BusyBox syntax validation, image checks, four negative format tests and
independent AOSP parsing passed. Hardware startup is unproven.
The exact kernel/initramfs also booted in ARM64 emulation with native PID 1 and
an interactive shell; see `EMULATED-FIRST-BOOT.md`.

## Stock restoration resources

`docs/stock-avb-audit.json` records AOSP AVB verification. Stock boot and vbmeta
signatures validate against their embedded key, the boot payload hash matches,
the signed vbmeta vendor_boot hash matches, and chained partition keys agree.
Vendor_boot's own metadata uses algorithm NONE; it is covered by the signed
parent hash. Deliberately corrupted signature copies were rejected in memory.
This confirms internal consistency; the OEM key is not independently trusted,
the phone's stored rollback indexes are unknown, and filesystem hashtrees have
not been checked. It is not a verified restoration path by itself.

The package includes an MTK_DA_v6 loader with hardware code 0x907. MTKClient's
MT6983 configuration selects XML protocol and DA code 0x907. This is a useful
offline match, not proof that Lynx accepts the loader or authentication file.
See `docs/download-agent-audit.json` and `docs/service-resource-audit.json`.

## Proposed sequence and boundaries

1. Assess a stock-mode MediaTek loader session for read-only GPT inspection.
   No exploits, security patching, unlock, erase or flash commands belong in
   this initial readback test. Stop on authentication or loader rejection.
2. If supported, read boot_a, vendor_boot_a, dtbo_a and vbmeta_a to workspace
   files; verify expected size, nonempty contents and hashes, and inspect the
   actual DTB and module ABI. A successful GPT read is not a full backup.
3. Establish exactly which saved images can restore every partition the Linux
   trial would change, and confirm a usable physical Fastboot return path.
   Preserve stock recovery entry or provide an independently verified recovery
   route. The existing custom init may intercept recovery, so this remains open.
4. Only after those checks, finalize a trial confined to the necessary slot A
   image. Do not touch slot B, preloader, lk, partition tables, userdata or super.
   Any additional vendor_boot/DTBO/vbmeta requirement changes the scope and must
   be evaluated before proceeding; never add a blanket verification-disable or
   both-slot command as an automatic fallback.
5. Observe the native PID 1 USB-console marker, uname and /proc/1/comm.
   If boot fails, return physically to Fastboot and restore the validated images
   for the changed partitions. This must be a prepared procedure, not improvised.

The second stock-loader probe reached DA stage 2 in RAM, then our guard stopped
on required session authentication. No GPT or partition backup was obtained.
See `STOCK-LOADER-AUTH-RESULT-20261010.md`. Thus enumeration and loader startup
are demonstrated, but authenticated readback/restoration is not.

No executable flash script is provided while restoration remains unverified.
The phone has not been flashed, erased or switched to another slot in this
work. Earlier Fastboot reboot commands were issued as recorded in
`RECOVERY-AND-FIRST-BOOT.md`. The stock-loader diagnostic trial contacted Lynx and uploaded the
loader into RAM only; no persistent phone state was intentionally modified.

`FASTBOOT-RESTORATION-PLAN.md` and `fastboot-restoration-audit.json` record the
subsequent offline image verification, concrete July-versus-August LK mismatch,
and unsuccessful manufacturer-CDN probes for an August reference OTA.

Protocol reference: https://github.com/bkerler/mtkclient
