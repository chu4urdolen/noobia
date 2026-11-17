# Lynx corrected boot_a trial, 2026-10-10

The user explicitly accepted remaining hardware uncertainty and authorized the second trial.
The guarded script verified the corrected image, stock undo, OTA reports, combined
ramdisk emulator evidence, AVB model, independent validation and fresh Fastboot preflight.
Fastboot accepted the 64 MiB corrected image into boot_a and accepted one reboot.
No other partition was written; no slot switch occurred.

Trial receipt: logs/boot-a-lz4-trial-1791604622698167232.json.
Fresh preflight: logs/fastboot-preflight-1791604622727838800.json.

The user initially reported Orange State staying on screen without restarting,
then reported a reboot. No Linux USB console was observed at that point.
Native Linux hardware boot is not proven. The reason for the reboot is unknown.
The user was asked to return to Fastboot for the authorized stock boot_a undo.
The user returned Lynx to Fastboot; stock boot_a restoration subsequently succeeded as recorded below.

Completed passive observation: logs/lynx-usb-observation-1791604631841027388.json.
Observation lasted 60.61 seconds; events: [{"elapsed_seconds": 0.01, "usb": [], "serial_devices": []}]. No phone commands were sent.

## Stock undo completed

The first undo attempt stopped during read-only preflight because the new USB
node /dev/bus/usb/001/028 lacked Aria access; no write was issued.
Receipt: logs/boot-a-lz4-trial-1791604744536513079.json.
A per-device ACL was applied with pkexec setfacl -m u:aria:rw to that USB node.
The guarded undo then passed fresh checks and Fastboot accepted the stock
64 MiB boot_a image (sending OKAY 1.497 s, writing OKAY 0.074 s).
Successful undo receipt: logs/boot-a-lz4-trial-1791604779070971869.json.

Final read-only preflight passed:
logs/fastboot-preflight-1791604788515561099.json.
Product, bootloader, unlocked status, slot A and partition sizes match the
pre-trial values. Slot B was not switched or written. No other partition was
written, and no reboot was issued after undo. Lynx is left in Fastboot.

Fastboot acceptance is not byte-for-byte readback or proof of stock OS/recovery
startup. Native Linux hardware startup remains unproven. No further flash is
part of this trial; continue diagnosis offline before proposing another.
