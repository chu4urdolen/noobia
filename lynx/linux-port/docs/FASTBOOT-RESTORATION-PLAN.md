# Lynx restoration preparation — 2026-10-10

## Concrete resources

`audit_fastboot_restoration.py` checks saved stock image hashes and compares
their lengths against the partition sizes previously reported by Lynx. Its
machine-readable result is `fastboot-restoration-audit.json`. All four files
passed integrity and size checks:

| Resource | Intended existing partition | Purpose |
| --- | --- | --- |
| stock-cph2493-A10/boot.img | boot_a | Stock kernel and generic initramfs |
| stock-cph2493-A10/vendor_boot.img | vendor_boot_a | Matching DTB and vendor/recovery ramdisk |
| stock-cph2493-A10/dtbo.img | dtbo_a | Matching device-tree overlays |
| stock-cph2493-A10/vbmeta.img | vbmeta_a | Stock verification metadata |

These are package resources, not backups read from the phone. The paths are
relative to `artifacts/`. A boot-only Linux trial would need a boot-only undo
operation; this table does not authorize replacing all four partitions.
Restoring a stock boot image alone does not guarantee a working recovery when
the installed vendor_boot and dtbo versions remain unknown.

## New evidence

The package's LK contains build string `1ce7dbc_202307030417` at two recorded
offsets. The installed bootloader returned
`k6983v1_64_45ca337_202308100614`. They are different builds. Keep the installed
LK and preloader intact; do not downgrade the bootloader to match the package.

Reference LK also contains rollback-error strings and a Fastboot idle-reboot
message. Static strings do not establish the installed bootloader's policies,
timeout, or whether any rollback protection affects a boot-only trial. They
cannot explain every previous reboot, and do not prove a failure diagnosis.

OnePlus's announcement confirms that CPH2493 received OxygenOS
13.1.0.561(EX01) with the August 2023 patch:
https://community.oneplus.com/thread/1398632557381156866
That is a candidate to investigate, not a deduction of Lynx's lost OS version.
Manufacturer-CDN links for the August 14 full OTA were discovered through a
third-party index; no third-party package claims were used as compatibility
proof. Bounded range probes returned:

| Manufacturer endpoint | Observed result |
| --- | --- |
| component-ota-afs.coloros.com | HTTP 404 |
| gauss-componentotacostmanual-cn.allawnfs.com | HTTP 403 |
| gauss-otacostmanual-cn.allawnfs.com | HTTP 404 |
| componentota-manual-cn.allawnfs.com | HTTP 404 |

`inspect_remote_ota.py` is preserved for future metadata inspection. It refuses
servers that ignore ranges, caps each read and total transferred data, and does
not contact the phone. No August payload or metadata was obtained in these
probes. The directory created for it must not be mistaken for a firmware copy.

## Recovery layout and next usable route

Observed Fastboot variables show A/B boot, vendor_boot, dtbo and vbmeta
partitions. The stock vendor ramdisk contains recovery components, and the
generic ramdisk overlays its init entry. No GPT read was obtained, so absence
of a separately named recovery partition is not conclusively established.
Do not create a partition or alter the GPT. An eventual recovery image must
work with the existing boot layout.

The physical return to bootloader Fastboot has already been demonstrated.
Firmware restoration writes and booting the restoration set have not been
tested. A non-destructive query cannot prove that a subsequent flash or recovery
boot will work. Therefore the present set is integrity-checked but not a
verified restoration route, and the candidate remains ineligible for flashing
under the current agreed conditions.

The next useful input is either a readback of the current boot chain or a
complete CPH2493 reference package whose boot-chain compatibility can be
assessed against the installed bootloader. The August full OTA is one lead.
Do not ask the user for a remembered OxygenOS version or restore Android first.
If all readback and matching-package routes remain unavailable, a trial using
the July reference would be an explicitly risk-accepted experiment, not a
verified restoration procedure. Prepare that proposal separately before any
request to relax the current conditions.

For a later approved trial, record fresh device identity, unlocked state,
slot A, relevant partition sizes and stable USB access. Identify exactly which
partition changes; prepare the corresponding restore file and stop conditions.
Leave slot B, LK, preloader, GPT, super and userdata untouched. Any failed
command ends the sequence; do not automatically erase, disable verification,
relock, switch slots or add extra flashes.

The native Linux candidate already passed exact-kernel/initramfs emulation;
see `EMULATED-FIRST-BOOT.md`. This investigation did not contact Lynx or change
any phone partition.

Rose subsequently supplied August service-package listings. Their download
endpoints returned HTTP 403; no package was obtained. Fifteen further CDN
probes returned 404. See `AUGUST-PACKAGE-INSPECTION-STATUS.md` for the access
report and the prepared local ZIP/AVB inspection commands.
