# Lynx: native Linux on the OnePlus Nord 3

**Current safety hold:** heating was reported and V19 lacks working battery/CPU
temperature readings and verified throttling. Hardware trials are paused.
See [the thermal findings](linux-port/docs/THERMAL-SAFETY.md). The image is a
networking milestone, not yet a thermally validated operating environment.
The [RAM-only sensor trial](linux-port/docs/SENSOR-TRIAL-RESULT.md) now verified
29 thermal readings after SSH, including SoC/CPU/GPU/memory. Battery temperature
and CPU frequency control remain unverified; the safety hold remains active.

Lynx is a OnePlus Nord 3 5G CPH2493, MediaTek MT6983, with an unlocked
bootloader. **Native BusyBox Linux, Wi-Fi, DHCP and pinned key-only SSH are
verified on hardware.** The working V19 image retains the matching August2023
OxygenOS stock kernel/modules and boots our own PID1 and initramfs.

Start with [the repeat procedure](linux-port/docs/REPEAT-V19.md),
[architecture and findings](linux-port/docs/V19-FINDINGS.md), and
[connection/restoration notes](linux-port/docs/NATIVE-WIFI-SSH.md).

The exact running init, startup scripts and timing supervisor are preserved in
[known-good-v19/runtime](linux-port/known-good-v19/runtime). The reconstruction
manifest records archive order, modes, hashes and stock-header changes.
`tools/rebuild_known_good.py` reproduced the64MiB working image byte-for-byte
without any earlier experimental image.

This repository publishes our source, diagnostics and documentation. Private
checkpoints, keys, network configuration, OEM firmware, downloaded tools,
raw phone logs and bootable images stay local and are ignored by Git. A fresh
clone needs the matching private input objects and stock firmware; the source
repository alone is not a ready-to-flash firmware distribution.

`linux-port/prepare_*` and versioned `tools/*trial*` retain the experimental
history. Use the V19 procedure for the working baseline. Older top-level init
templates and builders describe intermediate states and are not interchangeable
with the exact V19 snapshot. Inspect the inputs, guards and current handset
state before running a hardware tool.

The display is not initialized. USB gadget networking remains unproved. This
is not yet a full postmarketOS installation. Only boot_a changes are part of
the current repeat procedure; retain the matching stock restoration path.
