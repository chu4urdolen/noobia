# Linux trial against matching restored foundation

The user authorized continuation within the expanded recovery/native Linux scope.
The matching August stock boot_a/vendor_boot_a/dtbo_a/vbmeta_a foundation had
previously reached the recovery menu. The native supplier image was then
written only to boot_a. Companion images and slot B were not changed.

An initial attempt stopped at read-only preflight due to missing USB ACL on
bus 001 device 006. No write was issued in that attempt:
logs/boot-a-matched-trial-1791640615875413970.json.
After granting Aria access to that node, the guarded write and reboot passed:
logs/boot-a-matched-trial-1791640681221801751.json.
Candidate SHA-256: 20b76e5fee8e71ec703dfd37b6709c45f5b03c780a4bd40adb290ae998681fe5.
Sending boot_a OKAY 1.496 s, writing OKAY 0.108 s, reboot OKAY.

The user reported Orange State. The image has no display bring-up, so the
warning's persistence does not itself establish success or failure. The
success criterion remains the native PID 1 marker over USB serial. Passive
USB observation completed without a native console; hardware startup remains unproven.
The trial image is currently installed; stock boot_a undo has not been issued.

The user subsequently reported a restart and return to Orange State. The
trial did not establish stable native Linux hardware boot. Completed passive
USB observation: logs/lynx-usb-observation-1791640718404030206.json, elapsed 60.61 seconds.
The user was asked to return to Fastboot for stock boot_a undo, preserving
the matching vendor_boot_a, dtbo_a and vbmeta_a foundation. Undo is pending
physical Fastboot entry; the native trial image is still installed.

## Stock boot_a undo completed

The user returned Lynx to Fastboot and reported that the original logo had
disappeared. The Fastboot USB node was bus 001 device 007. Initial read-only
preflight timed out because the node lacked Aria access; no write was issued.
After a per-node ACL grant, the guarded stock boot_a undo passed fresh checks.
Fastboot accepted sending 64 MiB (1.496 s) and writing (0.063 s).
Receipt: logs/boot-a-matched-trial-1791641076790219715.json.
Final preflight passed: logs/fastboot-preflight-1791641091714172073.json.

The bootloader string, unlocked status, active slot A and partition geometry
match the baseline. The matching stock companion images remain in place;
slot B, bootloader and calibration partitions were outside the write scope.
No reboot was issued after undo. Lynx is left in Fastboot.
The changed-logo observation is recorded without attributing a cause; it is
not evidence of a successful Linux boot or a damaged bootloader by itself.
