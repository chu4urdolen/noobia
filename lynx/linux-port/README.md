# Lynx — BusyBox native Linux bring-up

**Current milestone: V19 has verified native BusyBox PID1, Wi-Fi, DHCP and
pinned key-only SSH on hardware.** Read [the repeat procedure](docs/REPEAT-V19.md),
[findings](docs/V19-FINDINGS.md), [connection and undo](docs/NATIVE-WIFI-SSH.md),
and [exact runtime snapshot](known-good-v19). Earlier observations below retain
their historical context; they predate the direct SSH proof.

Lynx is a OnePlus Nord3 CPH2493, MT6983, with an unlocked bootloader. All project files are under `/noobia/lynx` on Nexus.

The first controlled hardware test strongly supports native BusyBox execution: Lynx returned to Fastboot without reported button input after a normal reboot, and the reset log changed to the exact bootloader-mode value3 requested by our native init. No physical native console marker was captured, exact return latency was missed, and the full proprietary bootloader fallback/reset graph remains unproved. This is indirect evidence, not conclusive proof of native PID1 execution. It does not establish a working USB console, networking or SSH. See [the result](docs/NATIVE-BOOT-PROOF-RESULT.md) and [machine-readable evidence](docs/boot-proof-hardware-result.json).

Stock `boot_a` was restored after the proof, with no reboot. The proven image, sources, hashes, tests and exact restore command remain preserved. SlotB, the bootloader and calibration data were untouched during this trial.

The next milestone is a live BusyBox shell over USB, keeping the exact compatible stock kernel. Development will make driver loading and USB failures observable before adding a Linux distribution or rebuilding the kernel.

A timed repeat returned to Fastboot after about21.6seconds with the same reset
signature. A matching control with only the native reboot request removed had
no Fastboot return during180seconds. This strengthens the native-init inference,
conditional on untouched buttons/cable; a direct native console marker remains
unobserved. [Timed comparison](docs/timed-minimal-boot-comparison.json).
Stock boot_a was restored after the hold control without reboot. See the latest
session entry for current state and subsequent trials.

[Session history](docs/SESSION-STATE.md), [observed button sequences](docs/BUTTON-SEQUENCES.md), and [the prior README](docs/README-BEFORE-CONFIRMED-BOOT.md) retain the investigation and recovery history. Build outputs are preparation artifacts; every hardware trial requires the existing scoped authorization, matching firmware checks and verified boot_a restoration path.
