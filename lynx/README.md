# Lynx: native Linux on the OnePlus Nord 3

**Current milestone:** [Alpine ARM64 userspace, Python/Git/Make and a tested Nexus restore](linux-port/docs/ALPINE-USERSPACE.md)

Alpine, `strace`, Python, Git and Make ran in a RAM chroot alongside the
proven BusyBox PID 1 and SSH environment. A base-only checkpoint has been
restored under QEMU with the exact stock kernel; the development checkpoint
is queued for the next native session. The [optional offline startup stage](linux-port/docs/ALPINE-RUNTIME-STAGE.md)
reconstructs that environment from pinned local inputs in a cold VM and
verifies the working phone runtime without replacing its services. It can be
selected after power setup in the existing host-assisted boot-resume helper.
The complete combined fresh-boot hardware sequence remains untested.

[Further evidence](linux-port/docs/ALPINE-STARTUP-STORAGE.md): Alpine also boots
directly as PID 1 in an isolated stock-kernel VM; the live RAM chroot has
read-only kernel visibility, and the phone's UFS partition map is validated.
Alpine OpenRC 0.63.2-r0 has now also reached its default runlevel and powered
down cleanly as PID 1 under QEMU with the frozen stock kernel. This is still a
VM result; the handset's guarded V19 startup remains the hardware baseline.

Native SSH plus live ZY0603 battery temperature, charge,
pack voltage and signed current are verified on hardware. The
[battery monitor and resume procedure](linux-port/docs/BATTERY-MONITOR.md)
restored the tools automatically after a reboot of unchanged V19. SoC/CPU
sensors, frequency controls and CPU cooling interfaces are also verified.
The [CPU idle investigation](linux-port/docs/IDLE-POWER.md) identified repeated
failed deep-sleep entries. A reversible WFI fallback eliminated those failures
and reduced observed battery discharge current while SSH stayed available.
A [tested one-step soft-throttle policy](linux-port/docs/COOLING-CONTROL.md)
now runs alongside the independent temperature watchers in RAM.
The [repeatable runtime power setup](linux-port/docs/RUNTIME-POWER.md) verifies
existing settings and is available as an optional stage after battery resume.

Continuous operation with USB unplugged is explicitly authorized. Routine
timed/end-of-test shutdowns are disabled in the current session. Temperature
watchers remain active; raw samples are copied to a bounded host logger.
The global Linux-flash hold remains active. Charging control, active throttling
response, deep idle and overall thermal safety are not fully validated.
All extra drivers are loaded into RAM after pinned SSH; V19 itself is unchanged.

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
is not yet a full postmarketOS installation. Authorized image trials are limited
to boot_a; current runtime additions stay in RAM. Retain the matching stock
restoration path.
