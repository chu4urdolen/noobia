# Lynx boot_a-only hardware trial

User explicitly authorized a boot_a-only Linux trial, accepted the remaining
uncertainties, and authorized stock boot_a restoration through Fastboot on
failure. Recovery-related companion partitions and slot B must remain untouched;
stop on unexpected recovery behavior.

Before issuing the write, both image SHA-256 hashes and sizes were rechecked,
the Fastboot binary matched the recorded preflight, and complete stock OTA
integrity/signature reports and exact-candidate emulation were confirmed.
`tools/lynx_boot_a_trial.py` preserves those checks and fixed commands. Its
default mode is offline readiness only. The live write was preceded by a fresh
read-only Fastboot preflight; product, unlocked state, active slot A, bootloader
identifier, partition sizes and the 64 MiB download limit matched expectations.

Live command/result log:
`/noobia/lynx/logs/boot-a-trial-1791603257293021766.json`.

```text
Sending 'boot_a' (21088 KB)                        OKAY [  0.486s]
Writing 'boot_a'                                   OKAY [  0.046s]
Finished. Total time: 0.548s
Rebooting                                          OKAY [  0.000s]
```

The written image was the August native BusyBox candidate, SHA-256
`74bcda633bf85b2601629966e09e68e154863232f6493829b975bb277b3cf7f9`.
No flash command targeted any other partition. No erase, slot switch,
verification-disable, lock/unlock, or preloader operation was issued.

After reboot, no phone USB interface or ttyACM console was observed. The user
reported the Orange State restart loop. Native Linux startup on the physical
phone was not demonstrated. This does not identify whether the failure was
bootloader acceptance, kernel/device-tree startup, initramfs integration or USB
bring-up; a warning/logo alone provides no kernel diagnostics.

The authorized stock boot_a undo is required next, after returning physically
to Fastboot and rechecking identity. The prepared stock image is SHA-256
`a67f03d7b826b834c23653b67eaa6efa971eb70ef8af19eee4d33fb5fc7fe995`.
At the report's initial creation restoration was pending. The user subsequently
returned Lynx physically to Fastboot. The new USB node was `/dev/bus/usb/001/027`;
the first restoration preflight timed out for local access and issued no write.
After granting access to that node, a fresh full preflight passed and the
authorized stock boot_a restoration was executed.

Restoration log:
`/noobia/lynx/logs/boot-a-trial-1791603408230049125.json`.

```text
Sending 'boot_a' (65536 KB)                        OKAY [  1.499s]
Writing 'boot_a'                                   OKAY [  0.135s]
Finished. Total time: 1.635s
```

The final read-only check is
`/noobia/lynx/logs/fastboot-preflight-1791603441544349676.json`.
Identity, bootloader identifier, unlocked state, slot A and partition sizes
matched the earlier observations. Fastboot accepted the stock write; partition
readback remains unsupported, so a byte-for-byte on-device verification was not
obtained. No subsequent reboot or recovery-menu test was issued. Lynx was left
in working bootloader Fastboot. No unexpected recovery-menu behavior was reported.

The physical Fastboot return and stock boot_a write are now demonstrated. This
does not establish a working Android installation or a successful stock recovery
boot. The Linux hardware trial failed, and its failure stage remains unknown.
Future work should inspect image verification and ramdisk/DTB integration offline
before proposing another hardware trial. Do not add companion-partition writes
as a fallback to this completed trial.
