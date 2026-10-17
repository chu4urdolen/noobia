# Lynx self-booting Alpine work — 2026-10-18

The installed `boot_a` remains the proven V19 BusyBox Wi-Fi/SSH image. No
partition has been written during this work. The four-hour host logger at
`logs/battery-session-1792276725293904387/result.json` observes the current
unplugged RAM health trial; on-phone thermal, battery, cooling and supervisor
watchers run independently of the logger. The exact August stock `boot.img`,
previously successful Fastboot restore path and V19 image are preserved. The
active `SAFETY-HOLD.json` still forbids a new Linux flash.

## Independent boot sequence under development

V19 currently waits for a Nexus acknowledgement before remaining in BusyBox.
The separate V25c and V26 **offline** prototypes instead use an init-created
per-boot local marker, after the verified stock bootstrap and boot_a supplement
read. They do not require Nexus to acknowledge a successful boot. The intended
sequence is:

1. Frozen V19 stock kernel, matching bootstrap and verified supplement.
2. Check the reviewed device tree, calibration, gauge topology, and exact
   sensor/CPU module files; start local battery, thermal, cooling and health
   supervision before Wi-Fi. Failed health startup requests power-off and one
   supported bootloader return.
3. Run the unchanged V19 Wi-Fi worker. Require its own successful result,
   interface, DHCP address and a live Dropbear process; failed startup asks
   for one supported bootloader return. A Wi-Fi network is still needed for
   SSH, but no Nexus process is required for the phone to make that decision.
4. V25c remains in BusyBox as rescue PID 1. V26 additionally verifies the
   embedded Alpine/OpenRC root archive and live safety gate, extracts Alpine
   into RAM, binds `/proc`, `/sys`, `/dev`, and `/run`, and replaces PID 1 with
   OpenRC. A refusal before `exec` leaves the monitored BusyBox environment
   running.

V25c image: `artifacts/selfboot-health-v25c-offline/nord3-selfboot-health-untested.img`,
SHA-256 `587e4e8ec2a195a63a519ce0471003a337faf2d278cba994ee9dd4857b3bcc3a`.
V26 image: `artifacts/selfboot-alpine-v26-offline/nord3-selfboot-alpine-untested.img`,
SHA-256 `8fe2ae0f1ce022d00a360ffe5908bfca7692d767005e2b306ded589e434d0d65`.
Both are private 64 MiB files, inherit V19's network credentials, reuse its
exact kernel and boot header, and leave unrelated boot-image members unchanged.
They are **not installed**. Superseded V25 and V25b prototypes remain locally
preserved for audit; V25c moves health before Wi-Fi.

## Verification completed

- The V19 fresh-boot RAM health trial on the actual handset passed:
  `logs/autonomous-health-window-1792276571479014331/result.json`. The
  matching health archive is unchanged in V25c/V26; the `--run-local` authority
  gate is a new path and remains untried on hardware.
- Host and local health startup fixtures passed with fake devices:
  `artifacts/autonomous-health-start-check-1792277691870787392/` and
  `artifacts/autonomous-health-start-check-1792277691870801979/`. The local
  Wi-Fi fixture passed success and one failure-return case at
  `artifacts/wifi-local-supervisor-check-1792277774233011434/`. The local
  archive handoff fixture passed success, wrong hash and missing marker at
  `artifacts/autonomous-health-local-check-1792277789934091154/`.
- The host and local OpenRC safety guard passed thirteen synthetic checks,
  including missing local health/SSH markers, stale battery, gauge error,
  high temperature and missing cooling controls. The exact source test is
  reproducible with `tools/test_openrc_handoff_guard.py`.
- The V26 local handoff passed an exact-stock-kernel QEMU run at
  `artifacts/openrc-pid1-handoff-vm-1792277992464569388/result.json`:
  BusyBox early init, local guard fixture, Alpine OpenRC as PID 1, preserved
  early worker, health service adoption, and clean shutdown. QEMU substitutes
  fake sensors and does not exercise Lynx's radio or the complete V26 image.
- Both builders round-trip audited every primary and supplement member and
  rejected changed base-image hashes. The packed init and added scripts passed
  shell syntax checks. These are packaging and control-flow checks, not a
  handset boot proof.

## Persistence and recovery boundary

The V26 Alpine root is an immutable, verified payload in `boot_a`, extracted
into RAM each boot. This lets a fixed release survive power cycles but does
**not** retain package installs, logs or user data. The currently observed
`userdata` partition (`sdc85`, 238,605,533,184 bytes) has unknown contents;
its first 4096 bytes were neither an obvious ext4/F2FS superblock nor all
zero. Do not infer that it is empty. Neither `userdata`, `super`, GPT, slot B,
the bootloader, nor recovery foundations should be changed to create storage
without a separate read-only identification, a restorable backup, and a
reviewed filesystem plan. No persistent-storage write has been made.

V26 still inherits the early BusyBox Wi-Fi and Dropbear processes. Their
survival across PID 1 replacement passed in a VM with a generic worker, but
automatic on-phone restart if either dies is not built yet. Native charging,
charge termination and disconnected-network behavior are not validated.
Before any controlled `boot_a` trial, review those failure paths, validate the
exact V26 image against the current Fastboot device identity and stock undo,
arm a phone-contact collector **before** physical reboot, and keep USB
unplugged. If the phone or recovery behaves unexpectedly, stop rather than
switching slots or changing additional partitions.
