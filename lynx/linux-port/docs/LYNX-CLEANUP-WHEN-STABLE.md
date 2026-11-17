# Lynx cleanup after a stable finished system

Noob asked on 2026-10-30 to remove obsolete images, scripts, and backups once
Lynx reaches a stable finished state. Keep this as a deferred cleanup task;
do not delete the working V50 rollback or trial receipts during current V52
hardware bring-up.

When the final native Linux boot, display, Wi-Fi/SSH, battery management,
Bluetooth transport, and recovery procedure have passed a cold boot and a
restoration drill:

1. Inventory old boot candidates, one-shot installers, and `.before-*`
   service backups. Compare hashes and references in the code map and docs.
2. Keep one verified current image and one verified recovery image, with exact
   Fastboot commands and an offline copy. Archive unique diagnostic evidence.
3. Remove superseded candidates and redundant backup copies only after the
   replacement and recovery evidence are recorded. Update the code map and
   tool README to point to the surviving paths.

The V52 display bootstrap now accepts exact V50 and V52 boot hashes. Its
previous version is saved on Lynx as
`/usr/local/bin/lynx-display-bootstrap.before-v52-hash`; include it in that
later backup inventory. The current fix receipt is
`logs/v52-display-hash-guard-1793385069793236974.json`.
