# Lynx automatic health supervision — current RAM session

Lynx's V19 native BusyBox boot is reachable through pinned SSH on this boot
(`e1af6ca5-ca54-46e9-8cdf-9a1dbea56994`). The existing thermal watcher reads
CPU/SoC sensors every five seconds and requests power-off at 60°C. The existing
battery watcher reads the identified ZY0603-family gauge every five seconds and
requests power-off at 45°C. The tested cooling watcher applies one CPU cooling
step at 45°C and releases it at 40°C or below. These processes now run on Lynx,
independent of the host logger and SSH availability.

`linux-port/lynx-health-supervisor.sh` adds a RAM-only backstop. Every five
seconds it checks that all three watcher PIDs still refer to the expected
programs, that the gauge is present and its last error-free sample is no more
than 15 seconds old, that battery temperature and charge are valid, that at
least two CPU and one SoC sensors answer, and that all three CPU cooling
controls exist. At 45°C or above it requires the cooling step to be active.
Three consecutive failed checks request a safe power-off. It does not change
charging, calibration, partitions, CPU policy, or cooling controls itself.

The script passed seven synthetic cases, including stale battery data, hot
battery, missing sensor, missing cooling action at 46°C, and exactly one fake
power-off request after three failures:
`artifacts/health-supervisor-check-1792263737856087486/result.json`.
Its exact SHA-256 is
`b07060f2f20723ce41f04e8f8252cf236967a487c7648057afdd1c6a598fa09e`.
The hash-matched `--once` mode passed on the real phone, followed by three more
live samples five seconds apart. Continuous `--watch` mode was then started
in RAM; the first event and PID were checked. Receipts:
`logs/live-health-once-1792263713039686377/`,
`logs/live-health-three-samples-1792263744404436330/`, and
`logs/live-health-watch-start-1792263766214003510/`.

The new host logger at
`logs/battery-session-1792263786215525656/result.json` captures recent health
events with battery, thermal and cooling readings every ten seconds. Its first
sample showed 26.5°C battery, 77% charge, and 32–34°C CPU/SoC readings. The
older logger was stopped after the replacement was verified, without any phone
command. A later runtime-power verification passed at
`logs/runtime-power-setup-1792264159910202756/result.json`.

This is automatic **within the current RAM boot**. V19 does not yet start the
modules/watchers by itself after a reboot; a host-assisted setup is still
required. The next image must package the matching sensor/CPU modules, the
verified battery monitor, scripts and startup order, then prove them under the
exact stock kernel and in a supervised handset boot. Do not mistake this RAM
success for a self-starting or thermally certified phone image. The Linux flash
hold remains active.

The reviewed stock driver binaries and watcher scripts are now collected in an
inert, hash-checked archive at
`artifacts/autonomous-health-inputs/inputs.tar.gz`. Its manifest records the
exact stock-kernel release, source/build hashes, and all member hashes. The
closure audit at `artifacts/autonomous-health-closure/result.json` compares its
two module plans with the successful handset trial. It found four inserted
drivers in plan order. The plans also require `oplusboot`, `buildvariant`,
`oplus_project`, and `mtk_boot_common` to have been loaded by the stock
bootstrap. Those are deliberately absent from the compact archive; a future
boot stage must check their live presence before inserting anything. The audit
does not authorize automatic module insertion. Each boot must also repeat the
device-tree/calibration checks and the gauge DeviceType query before enabling
the battery monitor.

`linux-port/autonomous-health-preflight.sh` is a read-only gate for that next
stage. It requires the exact kernel release, the bootstrap modules proved by
the closure audit, matching device-tree hashes and absent-property checks,
valid bootloader calibration bounds, the unbound expected gauge topology, and
all six packed drivers. A six-case filesystem fixture at
`artifacts/autonomous-health-preflight-check-1792264353611654369/result.json`
passed, including refusals for a missing bootstrap module, changed device
tree, truncated calibration, already-bound gauge, and missing packed driver.
It has not been run at a fresh handset boot and performs no insertion. Its
input archive must be hash-verified by the boot loader before extraction.

`linux-port/autonomous-health-start.sh` is the next **offline candidate** for
the supervised post-SSH stage. It runs that preflight, inserts only the four
reviewed stock sensor/CPU modules, starts the temperature watcher, repeats the
same-boot gauge DeviceType query, loads the gated battery monitor, starts the
battery watcher, applies the tested WFI fallback, waits for a below-40°C
cooling start, then starts the health supervisor. An independent 180-second
timer requests power-off if an insertion blocks. Its plan and shell syntax
pass local checks. The script is not packaged into V19/V22 or run on Lynx;
module insertion, gauge setup, timing, and failure handling at unattended
cold boot remain unproven. A supervised trial and recovery review must precede
any flash.

After the first one-hour host logger ended, Lynx remained reachable and the
on-phone health supervisor passed again at
`logs/live-health-after-logger-1792275511617151253/result.json`: 23.5°C
battery, 63% charge, roughly 30°C CPU/SoC, and three cooling controls.
`configure_runtime_power.py --verify-only` passed at
`logs/runtime-power-setup-1792275522742700027/result.json`. A second,
four-hour host capture was started at
`logs/battery-session-1792275518601564562/result.json`; it is observational
only and may finish while the on-phone protection continues.

An OpenRC `lynx-health` service is now prepared in
`linux-port/openrc-lynx-health`. It adopts a verified early health process or
starts one after the live prerequisites pass; routine service stop leaves that
safety process running. The original signed Alpine/OpenRC root is preserved.
A separate archive containing the service and exact supervisor source is at
`artifacts/openrc-health-rootfs-export/alpine-openrc-health-rootfs.cpio.gz`,
SHA-256
`5398ad7ea3d10e3f48b2bc7273f3a0912f7551d654740161d8bdacdb6d97fd77`.
The production handoff script and service startup passed under the exact stock
kernel in QEMU at
`artifacts/openrc-pid1-handoff-vm-1792263949729710290/result.json`.
That VM substitutes a fake sensor worker because it has no Lynx hardware; it
does not validate boot-time module insertion or a new phone image. This archive
is an offline artifact, not installed on Lynx.

A separate V22 offline image now embeds that health-enabled OpenRC archive:
`artifacts/openrc-health-v22-offline/nord3-openrc-health-candidate.img`, SHA-256
`01ce287ace2ede31d272a2742f9562284c8b1b8148b8be1abd19b3b4e9068568`.
The builder pins the reviewed V21 parent, preserves its stock kernel and init
control flow, updates only nested OpenRC payload and payload size/hash metadata,
and round-trip checks the resulting 64 MiB boot image. The private image is
mode 0600 and remains local. V22 still uses V21's host-assisted prerequisites;
neither the new root archive nor the offline VM proves independent cold-boot
health startup. It must not be flashed while the thermal hold is active.

The host resume workflow now retries only the exact reviewed cooling-start
refusal (where it reached WFI verification but the cooling watcher withheld its
PID), up to three times after ten-second waits. Other power setup failures stop
without retry. Twenty offline fixture checks passed at
`artifacts/alpine-resume-sequence-1792263656831428178/result.json`. This removes
the manual retry needed during this boot while preserving the cooling script's
strict below-40°C startup guard.

The current Alpine 3.24.2 RAM environment includes signed Python, Git, and Make
packages. Its host checkpoint is
`checkpoints/alpine-runtime-1792263391851313235/result.json`; an exact-stock-
kernel offline restore passed at
`artifacts/alpine-checkpoint-restore-1792263530573631274/result.json`.
The first VM restore exposed a Makefile fixture quoting error, fixed in the
second run. No persistent phone storage was written.
