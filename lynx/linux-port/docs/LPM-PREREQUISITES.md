# Deep-sleep prerequisites: live-tree and stock-module review

The rejected-entry loop is established, but its exact rejecting callback or
firmware return remains unidentified. This review narrows the next work without
changing the running kernel's power-management configuration.

## Observed on Lynx

The kernel-exported live FDT was read over pinned native SSH: 445,089 bytes.
It contains the low-power platform node with `suspend-method="enable"`, its
CPU power-management SRAM and MCUSYS control nodes, MCUPM and SSPM nodes and
reserved-memory regions, and the SCMI firmware node. The low-power node's
`lpm-kernel-suspend` value is zero. Missing device-tree nodes are therefore
not the immediate explanation for these particular devices being inactive.

Read-only sysfs inspection found all four corresponding platform devices
unbound: MCUPM, SSPM, SCMI and `mtk_lpm`. The module survey found no LPM,
MCUPM, SSPM or SCMI modules resident; `firmware:scmi` remains on the deferred
probe list. A node's presence alone does not prove its firmware is ready.

The same session retained the WFI fallback, native SSH and original three
watcher PIDs. The last survey showed battery 21.8°C, 83% and −70 mA, with all
battery field errors zero. No platform driver was loaded during this review.

## Matching stock dependencies

The offline audit resolves the stock transitive dependencies of these roots:

| Module | Direct stock dependencies |
| --- | --- |
| mtk-lpm | none |
| mtk-lpm-dbg-common-v1 | mtk-cmdq-drv-ext, mtk-lpm |
| mtk-lpm-plat-v1 | mtk-lpm-dbg-common-v1, mtk-lpm |
| mtk-lpm-dbg-mt6983 | mtk-lpm-dbg-common-v1, mtk-lpm |
| mcupm | emi-mpu, mtk-tinysys-ipi, mtk-mbox |
| sspm-v3 | emi-mpu, tinysys-scmi |

The union contains 25 stock modules. All report the matching
`5.10.149-android12-9-o-g311738fbb5a8` kernel; shared imported symbol CRCs have
no conflicts. This is useful compatibility evidence, not proof that their
initialization is safe or that every dependency must be newly loaded. Several
dependencies already serve the working display/Wi-Fi/storage foundation.

## Why loading the platform module is more than a flag change

The published core code replaces idle-state entry callbacks with module-owned
wrappers and registers suspend callbacks. Its module exit does not restore
those callbacks. Platform setup initializes shared SRAM and CPU power counts,
registers CPU hotplug handlers, installs suspend behavior, and invokes the
vendor firmware's power-state validation control with a SET action.

The wrapper is defined in `drivers/misc/mediatek/lpm/inc/lpm_module.h` and
ultimately uses the vendor low-power secure-monitor interface. Its source
returns the monitor's result, but the platform initialization call does not
check that result before completing initialization. Successful module insertion
alone would therefore not prove successful firmware validation.

The prerequisite review should next cover the MCUPM/SSPM mailbox and firmware
startup paths, then determine the minimal module sequence needed for a bounded
trial. Keep deeper states disabled during initial module bring-up. Do not
assume `rmmod` reverses the core/platform hooks; a recovery reboot must be
planned before testing those modules. No raw firmware control call was issued,
and no module or partition was modified for this audit.

The source commit is `81ec42ad5e803be0cba619f9f7bb298db7d33d7b`; it is not the
exact stock binary commit `g311738fbb5a8`. Conclusions about initialization are
source-guided hypotheses until checked against the matching binaries/runtime.

## Preserved evidence

- `logs/live-sleep-prerequisite-survey-1792178843537269212`: resident module
  subset, deferred devices, exported FDT and platform-device inventory.
- `logs/live-live-fdt-power-review-1792178869180168988`: hash-verified raw live
  FDT and `power-tree-analysis.json`; the raw tree remains private.
- `logs/live-sleep-driver-binding-check-1792179002427206853`: unbound drivers,
  current battery snapshot and original watcher PIDs alive.
- `artifacts/lpm-firmware-source-review-1792178466467282731`: eleven source
  files, immutable commit, hashes and captured command errors.
- `artifacts/lpm-bootstrap-headers-1792179001805511237`: firmware wrapper and
  platform headers with hashes.

`tools/audit_live_power_tree.py` reproduces the offline analysis from a verified
capture. It checks the capture hash, parses the tree, preserves selected power
properties, resolves dependencies and checks shared stock import CRCs. It
neither contacts Lynx nor inserts modules.

## MCU startup follow-up

Eleven pinned source files were preserved at
`artifacts/mcu-startup-source-review-1792179403259415815`. MCUPM's probe sets up
IPI/mailboxes, optional shared-memory/EMI protection, platform services and
timesync, then starts a receive worker. That worker can write MPAM cache
partition registers in response to firmware messages. The remove function
explicitly leaves IPI/memory cleanup unimplemented; module exit does not
unregister the driver or stop the worker.

The published MCUPM source and matching stock binary both contain the shared
memory compatible key `mediatek,reserve-memory-mcupm_share`. The live tree has
no node with that exact compatible. Its differently named MCUPM reserved region
does not prove equivalence. The source explicitly treats the missing shared
node as a supported logger-disabled path, not a fatal probe failure; do not
mistake this observation for proof of the sleep rejection's cause.

SSPM v3 initializes reserved memory, SCMI platform service, timesync and EMI
protection. Its probe ignores the internal module-init return, and its exit
also lacks cleanup. Driver binding alone would not prove readiness. Even the
read-only-looking `sspm_alive` sysfs attribute sends a SCMI SET request; it is
not a passive memory observation.

These findings argue for a separate, recoverable MCU trial rather than loading
the drivers into the useful current session and expecting `rmmod` to undo
everything. No MCU module or firmware command was used here. Work continued
on the [normal Linux userspace foundation](ALPINE-USERSPACE.md), which now
provides native APK and `strace` while the working power setup remains active.
