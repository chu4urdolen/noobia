# V25g supervised trial runbook

Status: **prepared, unexecuted**. Lynx currently has the verified V19 image
on `boot_a`, pinned Wi-Fi SSH, RAM-only health monitoring, and an Alpine
development chroot. The private Alpine checkpoint and exact stock/V19 restore
images are preserved on Nexus. Do not disrupt this session merely to repeat
an unexplained boot failure.

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
Return physically to Fastboot without slot switching. The known functional
Linux rollback is to arm a fresh V19 pinned collector, then run
`python3 tools/restore_v19_boot_a.py --flash --collector-receipt
<fresh-V19-collector-result.json>` after its fresh exact-identity checks; the
matching August stock `boot_a` is also
available through the flasher receipt's restore command. Neither undo should
run on an unexpected Fastboot identity or slot.

V25g has not booted on Lynx. The handset-side BusyBox gzip/cpio parser did
accept its exact supplemental payload in a RAM-only test, and the observer's
beacon path was exercised against live V19. Neither result proves the full
V25g image or native charging works.
