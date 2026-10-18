# V25g supervised trial runbook

Status: **V25g's first unplugged trial produced no network contact; proven V19
was restored to `boot_a` and awaits an unplugged boot**. The guarded write
receipt is `logs/v25g-boot-a-trial-1792333616762100475.json`. The host did not
reboot; Lynx remained in Fastboot on USB at the last check. The private Alpine
checkpoint and exact stock/V19 restore images are preserved on Nexus. The
steps below record the preparation and recovery procedure; do not repeat the
write while it is already installed.

## Preflight and observation

1. Keep USB disconnected during native boot. When a supervised physical trial
   is possible, arm `python3 tools/observe_v25f_diagnostic.py --arm --seconds
   900 --candidate v25g` first and retain its `result.json` path. The observer
   listens at the pinned Noobia collector and follows a valid Lynx beacon to
   its actual DHCP address. It sends no phone write or V19 acknowledgement.
2. Return Lynx to Fastboot through the previously proven local reboot helper,
   only after saving useful live RAM work. Connect USB once Fastboot is on
   screen. Run the separate read-only exact-identity Fastboot preflight.
3. Run `python3 tools/flash_v25g_boot_a.py --flash --observer-receipt
   <fresh-observer-result.json>`. The tool rechecks the exact 64 MiB candidate,
   stock undo, OTA evidence, Fastboot binary, image-specific exception and
   live identity/slot before writing **only `boot_a`**. It does not reboot.
4. Disconnect USB, then boot from Fastboot using the phone controls. Do not
   let the unvalidated native image start with a charger attached. Watch the
   observer's raw beacon/SSH records, boot log, health proof and any automatic
   power-off. A black screen alone is not a diagnosis.

## Stop and recovery

Stop if Fastboot identity or slot differs, the phone warms unexpectedly,
the candidate behaves differently from its bounded timer, or no authenticated
SSH/health proof appears. Preserve the observer and expdb/pstore receipts.
If a failed candidate leaves no live SSH log, use a later read-only V19 boot
to capture expdb with `tools/capture_expdb_live.py`, then compare its
documented first 0xF0000 bytes against the baseline with
`tools/compare_expdb_captures.py` before assigning log age.
Return physically to Fastboot without slot switching. The known functional
Linux rollback is to arm a fresh V19 pinned collector, then run
`python3 tools/restore_v19_boot_a.py --flash --collector-receipt
<fresh-V19-collector-result.json>` after its fresh exact-identity checks; the
matching August stock `boot_a` is also
available through the flasher receipt's restore command. Neither undo should
run on an unexpected Fastboot identity or slot.

V25g has no verified native boot on Lynx. The handset-side BusyBox gzip/cpio parser did
accept its exact supplemental payload in a RAM-only test, and the observer's
beacon path was exercised against live V19. Neither result proves the full
V25g image or native charging works.

During the first V25g trial, the Fastboot USB protocol remained available even
when Lynx's display was black. Noob then disconnected USB and started the phone
with Power only; the orange screen appeared. The renewed read-only observer at
`logs/v25g-diagnostic-observer-1792333989111901562/result.json` logged 83
unsuccessful SSH probes and no valid Wi-Fi beacon over more than four minutes
after the unplugged start. This does not locate the boot failure. The observer
was stopped after its evidence was saved, and a V19 recovery listener was armed
at `logs/wifi-v19-contact-1792334500503425456/result.json`. Fastboot then
reconnected with the exact serial. The guarded V19 rescue wrote only `boot_a`
successfully at `logs/v19-rescue-boot-a-1792334760095554872.json` and did not
reboot. An unplugged V19 boot and pinned SSH contact remain to be verified.
