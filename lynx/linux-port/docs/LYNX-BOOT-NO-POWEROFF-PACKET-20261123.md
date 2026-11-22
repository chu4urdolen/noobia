# Install packet (proposal): Lynx boot image that never powers off on a refused hand-off

Author: Gwyn, 2026-11-23, after Tom asked: no reboot loops, nothing that
reboots Lynx. **Not built, not flashed.** Needs two reviewers other than the
author (Dushich can be one), and Aria builds and installs it, with Tom present.

## What happened

On the night of 2026-11-22/23, Lynx powered off at about 300 s of uptime on
almost every boot, and finally the bootloader stopped in fastboot.

- The early-boot tail in the V53 image (`lynx-v44-local-openrc-tail.sh`)
  attempts the hand-off to Alpine after 3 good health samples.
- When `persistent-openrc-handoff.sh` refuses, the tail falls through. It
  **powers off** at 300 s (`V44_OBSERVATION_COMPLETE; POWER_OFF_REQUESTED`).
- The hand-off was refused for two reasons:
  1. **A hash mismatch.** Gwyn edited `/etc/init.d/lynx-health`, which is
     pinned by SHA-256 together with `/sbin/openrc-init` and
     `/lib/ld-musl-aarch64.so.1`. That edit has been restored.
  2. **A warm boot.** `openrc-handoff-guard.sh` requires every CPU and SoC
     zone to be below 48 °C.
- The tail also powers off after 3 failed health samples, and when the
  `HANDOFF_BEGIN` record fails.

## The change

Replace `lynx-v44-local-openrc-tail.sh` with
[`lynx-v54-local-openrc-tail.sh`](../lynx-v54-local-openrc-tail.sh):

- **No poweroff or reboot, anywhere.**
- **A refused hand-off keeps the BusyBox rescue running.** SSH stays up on
  port 22, and the hand-off is retried every 30 s once 3 health samples pass
  again. A warm boot therefore waits until she has cooled, then continues.
- **Failed health samples apply CPU soft throttling** and keep waiting.
- Everything else is unchanged: the guard, its 48 °C limit, the three hash
  pins and the host confirmation. They still decide *whether* to hand over;
  they just can no longer switch Lynx off.

## Consequences to handle in the same packet

- A new boot image changes the boot partition's SHA-256. **21 tools in
  `lynx/tools/` pin the V53 hash** `c0474552…c23c75e` (`EXPECTED_BOOT_SHA`).
  Among them are `prepare_camera_camsv.py`, `probe_camera_ram.py` and
  `probe_camera_pipeline_ram.py`. Find them all with:
  `grep -l c047455271828cf9bfa90984eea121d8ede8754f6297fc06f33f1e99fb23c75e lynx/tools/*.py`.
  Add the V54 hash next to the V53 one rather than replacing it, so rollback
  keeps working.
- The boot-image builder for V53 and its receipts:
  `lynx/tools/lynx_boot_a_v53_trial.py`, `docs/CURRENT-HANDOFF.md`.

## Install (Aria, attended)

1. Build V54 from the V53 recipe with only the tail replaced. Record the
   SHA-256.
2. Preflight: Lynx is cool, charging, and on a USB cable to Nexus.
   `fastboot getvar current-slot` reports `a`.
3. Flash slot **b** only, then make it active. Slot a keeps V53.
4. Verify: Alpine comes up. Then force one refusal, for example by booting
   warm, and confirm that she stays up in rescue (SSH on port 22), logs
   `V54_LOCAL_OPENRC_REFUSED`, and hands over once she's cooler.
5. **Disable switch:** none is needed, because nothing in V54 acts on its own.
6. **Rollback:** `fastboot set_active a` (V53), using the same cable.
