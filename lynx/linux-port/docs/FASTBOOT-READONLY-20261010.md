# Lynx: read-only Fastboot recheck, 2026-10-10

The user entered Fastboot physically and connected Lynx to Nexus. USB appeared
as MediaTek 0e8d:201c, bus 001 device 010. A temporary per-device ACL restored
access for aria; no persistent USB rules were changed.

Commands were limited to `fastboot devices`, `getvar all`,
`getvar battery-voltage`, and `getvar battery-soc`.

Observed values:

- Serial: 89BYAY5L4T9HFUOV
- Product: k6983v1_64
- Bootloader: k6983v1_64_45ca337_202308100614
- Baseband: MOLY.NR16.R1.MP3.TC16.PR1.SP.V5.P83
- Unlocked: yes; secure: no; is-userspace: no
- Current slot: a; slot count: 2
- Slot a successful: yes; slot b successful: no
- Both slots unbootable: no; both retry counts: 7
- boot_a/b and vendor_boot_a/b: 0x4000000 bytes each
- dtbo_a/b and vbmeta_a/b: 0x800000 bytes each
- super: 0x380000000 bytes
- Maximum download: 0x4000000 bytes
- off-mode-charge: 1
- Battery voltage and state of charge: empty responses, not usable readings

These values do not identify the installed OxygenOS build. Slot success flags
are bootloader metadata, not evidence that the current system boots. Firmware
compatibility and recovery preservation remain unresolved. No reboot, slot
switch, download, flash, erase, format, lock, or unlock command was issued in
this recheck. Lynx was left in Fastboot.
