# Lynx August firmware and native Linux preparation

Subsequent hardware result: an explicitly authorized boot_a-only Linux trial
failed to produce a USB console and returned to Orange State looping. Physical
Fastboot was recovered and Fastboot accepted the verified stock boot_a undo.
Lynx remains in Fastboot after successful read-only checks. No companion
partition or slot B was written. See `BOOT-A-TRIAL-RESULT-20261010.md`; earlier
preparation and untested-restoration statements below describe the state before
that trial. Stock recovery startup and byte-for-byte partition readback remain
unverified.

Final download result: the full OTA is saved as
`/noobia/lynx/downloads/CPH2493_13.1.0.561_230814-eu-ota.zip`.
All download-range hashes and ZIP member CRCs passed; the complete payload hash
matched its declared FILE_HASH. The entire payload RSA signature also verified
against the included OTA certificate. This does not independently establish
OEM-key trust or a tested physical restoration procedure.
Archive SHA-256:
`3ef04099170d28f9f422b1748b86847d65f2c0f1741bd429be720b51d3c92e70`.

## Identified reference

Working manufacturer-hosted OTA:
https://gauss-opexcostmanual-eu.allawnofs.com/remove-59822b61319727ba9ca6f2fd62dc0ef2/component-ota/23/08/14/4f1a650f088f4be39da1e6103015aa24.zip

ZIP length: 5,648,922,659 bytes. Payload length: 5,648,917,013 bytes.
Internal metadata identifies CPH2493EEA, OP556FL1, project 21871,
`CPH2493_13.1.0.561(EX01)`, OTA ID
`CPH2493_11.A.12_0120_202308141443`, and security patch 2023-08-05.
This is stronger evidence than a download filename or matching month.

The extracted LK contains `45ca337_202308100614`, matching Lynx's recorded
Fastboot identifier `k6983v1_64_45ca337_202308100614`. No LK image is to be
flashed. A matching build string is not a byte-for-byte readback of the
installed bootloader, and does not establish the versions of every partition.

## Integrity evidence and full download

Metadata SHA-256 matches payload properties. The metadata RSA-2048 signature
validates against the certificate contained in the ZIP, and corrupted metadata
is rejected. Selected partition operation hashes and complete reconstructed
partition hashes match the manifest. All selected partitions have no old
partition dependency. Although this vendor payload declares minor version 7,
its selected operations are only REPLACE, REPLACE_BZ, REPLACE_XZ and ZERO;
no old Android data is needed to reconstruct these images.

Stock boot and vbmeta signatures validate against their embedded AVB key.
Boot/vendor_boot payload hashes and chained keys agree. The signing keys match
the retained July CPH2493 reference. DTBO has no standalone AVB footer and
is checked against the signed payload manifest. These checks demonstrate
internal consistency; independent OEM-key trust and Lynx's stored rollback
indexes are not established.

The complete ZIP was downloaded separately. Its recorded transfer state
is `/noobia/lynx/downloads/august-eu-parallel-download.json`.
`verify_downloaded_august_ota.py` automatically checks every downloaded range,
whole-ZIP SHA-256, all ZIP member CRCs, metadata consistency and the entire
payload's declared FILE_HASH once the transfer finishes. Its authoritative
result is `/noobia/lynx/downloads/august-eu-ota-integrity.json`.
Only state `verified` means those complete-download checks passed. A pre-sized
`.parallel.part` file is incomplete even though its apparent length is full.
After those checks passed, `verify_august_payload_signature.py` verified the
entire payload's RSA signature using AOSP's Android 13 signed-byte definition.
Its result is `downloads/august-eu-payload-signature.json` under the task root.
Independent OEM-key trust remains separate from signature consistency.

## Stock recovery resources

The extracted stock images are in `artifacts/stock-cph2493-August-eu-ota`.
Android boot and vendor_boot headers are both version 4. Vendor_boot has one
platform ramdisk and an MT6983 DTB with a 64-byte wrapper. DTBO has six parsed
device-tree entries. Stock generic `/init` and vendor recovery executables,
configuration and module lists are present. Their presence does not prove
that recovery will start on the physical phone.

The original layout supplies recovery through the boot chain. The actual GPT
has not been read, so no separate recovery-partition absence is asserted as a
proven inventory. No new partition, slot switch or storage layout change is
needed for this preparation.

`downloads/lynx-August-recovery-reference.zip` under the task root is a local
reference bundle of the six boot/verification images and audit snapshots.
Its own CRCs and included-image hashes passed. It is not an OEM service ZIP;
it includes no bootloader/preloader image or executable flash script.
Its receipt is `downloads/lynx-August-recovery-reference-receipt.json`.
After complete source verification, `build_august_recovery_reference.py
--verified-source` can produce a separate `lynx-August-recovery-verified-source.zip`
with both full-download verification reports. This still does not imply that
physical restoration has been tested or that a flash is authorized.
This verified-source bundle has now been produced. Its successful CRC/image
hash receipt is `downloads/lynx-August-recovery-verified-source-receipt.json`.

## Updated native Linux candidate

The August kernel release is `5.10.149-android12-9-o-g311738fbb5a8`.
It differs from the July kernel previously used. A separate native BusyBox
candidate now reuses this exact August kernel and 24 USB modules extracted
from the same August vendor ramdisk. Their hashes, dependency closure,
version strings and symbol-version sections were checked. The old image and
its emulation evidence remain preserved.
The embedded August kernel configuration was independently extracted:
devtmpfs is disabled, while proc, sysfs, tmpfs, initrd/gzip, ELF, USB configfs,
ACM and ECM are enabled. MTU3 is a module and MODVERSIONS is enabled.
The manual `/dev` approach is therefore appropriate for this exact kernel.
The configuration and selected-option report are preserved beside the images.

New candidate: `artifacts/busybox-August/nord3-busybox-candidate.img`.
Size: 21,594,112 bytes. SHA-256:
`74bcda633bf85b2601629966e09e68e154863232f6493829b975bb277b3cf7f9`.
Independent image validation passed. The exact new kernel/initramfs booted in
an isolated ARM64 emulator: native `/init` was PID 1, the interactive shell
reported `aarch64`, and devtmpfs mount count was zero. Evidence is in
`artifacts/emulated-boot-August/result.json` and its console log.

This is native Linux, without Android init or HALs during normal startup.
The emulator deliberately excludes the physical USB controller and stock
vendor ramdisk. USB on Lynx, display, and recovery handoff remain untested.

## Restoration assessment and future trial boundary

The package supports preparing a coherent stock boot-chain restoration set,
and removes the previous reference-LK build mismatch. It is not a tested
restoration procedure: no partition write or stock recovery boot has been
performed, and the on-device vendor_boot/DTBO have not been read back.

A later proposed first Linux trial should be confined to `boot_a` where
compatible with the installed vendor boot chain. Its intended undo resource
is the verified August `boot.img`, through the demonstrated physical Fastboot
entry. Replacing vendor_boot or dtbo to obtain a coherent stock recovery set
would change additional partitions and requires a separately assessed scope;
the existence of this bundle is not permission to flash all its contents.

Before proposing any write: require the complete ZIP integrity result, record
a fresh read-only Fastboot identity/slot/partition-size check and reliable USB
access, specify the exact changed partition and undo command, and explain
what remains untested. No Android restoration is required first. If recovery
preservation still cannot be established without an experiment, present that
uncertainty explicitly rather than claiming the path is verified.

Current instruction is investigation only. `flash_eligible=false`; no phone
partitions were flashed or erased, no slots changed, and Lynx was not contacted
for this August investigation.

## Reproduction

From this workspace, `make build-august`, `make check-august` and
`make emulate-august` provide the following explicit commands. Ordinary `make`
targets retain the earlier July candidate for reproducibility.

```sh
python3 build_busybox_image.py \
  --stock-dir artifacts/stock-cph2493-August-eu-ota \
  --stock-manifest artifacts/stock-cph2493-August-eu-ota/package-inspection.json \
  --vendor-audit docs/august-vendor-ramdisk-audit.json \
  --output artifacts/busybox-August
python3 validate_image.py --directory artifacts/busybox-August \
  --stock-boot artifacts/stock-cph2493-August-eu-ota/boot.img
python3 emulate_first_boot.py --candidate-dir artifacts/busybox-August \
  --output-dir artifacts/emulated-boot-August
```

Tools, source references and data are kept under `/noobia/lynx`.
