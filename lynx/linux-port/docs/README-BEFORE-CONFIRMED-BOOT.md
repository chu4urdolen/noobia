# Lynx — native Linux bring-up

Lynx is the OnePlus Nord 3 CPH2493, MediaTek MT6983, bootloader product
`k6983v1_64`. This workspace is on Nexus. Argus is used only as an ARM64 host
for BusyBox applet and shell-syntax checks; the phone image is packaged on Nexus.
No phone image is installed on Argus. Argus's unrelated NVMe restoration is
tracked under `/noobia/lynx/argus`.

## Current result

Latest: the clock-provider variant was written to boot_a but produced no native
USB console in its observation window. A separate unconditional watchdog/USB
startup variant passed ARM emulation without the custom USB boot argument,
independent validation and AVB model controls. It is prepared, not flashed;
the preceding clock variant remains installed pending Fastboot return.
See `docs/ALWAYS-USB-DIAGNOSTIC.md`.

Latest: the stock-metadata native diagnostic was installed into boot_a and
produced no native USB console; the user reports Orange State. Stock undo for
that specific diagnostic is pending. A confirmed omitted I2C clock provider is
fixed in a separate 34-module candidate, which passed offline validation,
AVB model controls and module/shell emulation. It is ready for a boot_a-only
trial after physical Fastboot return. See `docs/I2C-CLOCK-FIX.md`.

After the user expanded restoration authority, the matching August stock
boot_a, vendor_boot_a, dtbo_a and vbmeta_a images were written successfully.
The user subsequently reached the recovery menu; recovery ADB remains absent.
The bootloader, calibration data and slot B were not written. A boot_a-only
native Linux trial is prepared against this matching baseline, with stock
boot_a undo. It was executed against the new baseline, but Lynx restarted and no native
USB console appeared. Stock boot_a undo succeeded; final Fastboot checks passed.
See `docs/MATCHED-FOUNDATION-LINUX-TRIAL.md`.
See `docs/MATCHED-STOCK-BASELINE.md` for current state.

An offline review of Rose's mtk-log-util lead confirms MT6983 recognition and
matching pstore coordinates, but finds no independent route around the existing
DA session-authentication barrier. The wrapper's default acquisition can enter
automatic security-handling paths; it has not been connected to Lynx.
See `docs/MTK-LOG-UTIL-REVIEW.md` for the pinned source audit and recommendation.

The next offline investigation found missing watchdog and USB supplier drivers.
A separate 33-module diagnostic candidate now passes structural and AVB checks,
combined-ramdisk emulation, and a VM run that executes every module insertion.
A third authorized phone trial produced no Linux USB console within 60 seconds.
Stock boot_a was restored successfully and final Fastboot checks passed; Lynx
is left in Fastboot. See `docs/BOOT-A-SUPPLIER-TRIAL-RESULT-20261010.md` and
`docs/EARLY-BOOT-SUPPLIERS.md`
for the evidence, proposed third trial and remaining hardware uncertainty.

Offline investigation reproduced a failure in the original August packaging:
combining the stock legacy-LZ4 vendor ramdisk with our gzip generic ramdisk
causes an initramfs decoding failure and a PID 1 crash in the ARM emulator.
A separate corrected candidate uses legacy LZ4 and a boot-local AVB footer.
The combined stock-vendor-plus-native ramdisks now reach an interactive BusyBox
shell. Independent structural checks and the unlocked-policy AOSP AVB model
also pass their expected assertions. A second explicitly authorized hardware
trial was then performed: Lynx stayed at Orange State briefly, then rebooted,
and no Linux USB console appeared. Stock boot_a was restored successfully;
final checks passed and Lynx is left in Fastboot. See
`docs/BOOT-A-LZ4-TRIAL-RESULT-20261010.md`.
See `docs/BOOT-PACKAGING-FIX.md` for evidence, remaining limits and a proposed
second boot_a-only trial with its exact stock undo command.

An explicitly authorized boot_a-only August Linux hardware trial was attempted.
Fastboot accepted the Linux write, but Lynx returned to the Orange State loop
and exposed no Linux USB console. The user returned her physically to Fastboot;
the verified August stock boot image was then written back to boot_a successfully.
Final read-only identity/slot checks passed. Lynx is left in Fastboot. No other
partition was written and slot B was not switched or flashed. See
`docs/BOOT-A-TRIAL-RESULT-20261010.md` for the exact commands and observed limits.

The working August CPH2493 manufacturer OTA has now been identified and its
boot-chain images reconstructed and hash-checked. Its LK build string matches
Lynx's recorded bootloader. A separate August-kernel native Linux candidate also
passed interactive ARM emulation. The full ZIP is downloaded; archive CRCs,
payload hash and the whole-payload signature against its included certificate
passed. Final reports are under `/noobia/lynx/downloads`.
See `docs/AUGUST-RECOVERY-AND-LINUX.md` for current evidence and limitations.

The exact kernel and initramfs from the current candidate have booted in an
isolated ARM64 emulator. Native `/init` ran as PID 1, `mdev -s` completed, and
interactive shell commands confirmed `aarch64` with zero devtmpfs mounts.
This validates basic userspace startup, not Lynx's peripherals or restoration.
See `docs/EMULATED-FIRST-BOOT.md` and `artifacts/emulated-boot/result.json`.

A minimal native BusyBox initramfs and Android-header-v4 boot candidate exist.
The exact stock kernel and 24 matching USB-support modules are reused. Normal
startup runs native BusyBox PID 1, with manual device nodes and `mdev`, plus a
USB serial console and an ECM Ethernet attempt. No Android init or HAL is used
for this candidate. SSH, display, audio, Wi-Fi and modem are later milestones.

The first phone trial downloaded the image into RAM but `fastboot boot` was
rejected as an unknown command. Fetch was unsupported; fastbootd did not start.
The physical recovery menu was reached, but exposed no USB/ADB connection.
No partition was flashed or erased in those earlier RAM-boot/readback attempts.
Lynx later returned to Fastboot for read-only
slot checks; slot A reports successful=yes, unbootable=no, retries=7. Slot B
remains unverified and untouched. Recorded flags do not prove a working OS.

## Offline build and checks

For the new August reference, use `make build-august`, `make check-august` and
`make emulate-august` from this directory. All three operate offline and never
contact Lynx. The original default targets below retain the July reference for
reproduction of earlier work.

For the corrected candidate, use `make check-august-lz4` and
`make emulate-august-lz4`. These include boot-local AVB checks and the actual
vendor-before-generic ramdisk combination. They never contact the phone.

```sh
cd /noobia/lynx/linux-port
make build
make check
```

Builds use cached, hash-bound ARM64 validation evidence. After changing `init`
or BusyBox, refresh that evidence with `make validate-arm64`. This sends the
binary and script to Argus, runs the applet list and syntax check, and never
executes the init script. Ordinary builds and checks are fully offline.

New outputs are under `artifacts/busybox-offline`; the original attempted
candidate and trial logs remain under `artifacts/busybox-first-boot`.
Stock reference components remain under `artifacts/stock-cph2493-A10`.

## Gates before a stored-image test

The reports deliberately set `flash_eligible=false`. The July 2023 stock
package matches CPH2493 but has not been matched to Lynx's installed firmware.
Current boot/vendor_boot/DTBO/vbmeta backups have not been obtained. Replacing
generic `/init` may affect Android recovery entry, and preservation of that
entry is not validated. These are unresolved recovery requirements, not reasons
to bypass the user's instruction against partition modification.

Android is assumed lost and may be discarded. Restoring Android is not a gate
for native Linux. The preservation requirement concerns bootloader access and
a usable repair route after a failed experiment. See
`docs/CONTROLLED-LINUX-TRIAL.md` for the current candidate, slot observations,
stock verification results and proposed readback/rollback sequence.

See `docs/RECOVERY-AND-FIRST-BOOT.md` for observed recovery behavior and
`docs/stock-component-manifest.json` for stock-image provenance.
See `docs/FASTBOOT-RESTORATION-PLAN.md` for the checked restoration resources
and remaining compatibility/recovery requirements.
`audit_recovery_boundary.py` records the stock init/recovery files and exact
ramdisk overlap in `docs/recovery-boundary-audit.json`. It shows why keeping
vendor_boot unchanged alone does not establish recovery preservation.

## postmarketOS direction

The first milestone remains an observable native Linux boot. A full
postmarketOS port will need devtmpfs support or a deliberate initramfs adaptation,
and matching module ABI validation if the kernel is rebuilt. The inspected
pmaports checkout has no vitamin/MT6983 port. A draft device definition is kept
outside the active pmaports tree so it cannot accidentally be treated as a
supported install target. Hardware compatibility and successful boot remain
unproven.
