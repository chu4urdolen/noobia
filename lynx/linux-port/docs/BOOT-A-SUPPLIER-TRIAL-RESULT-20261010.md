# Lynx supplier-image trial, 2026-10-10

The user authorized this third boot_a-only image trial, with stock restoration
if it fails. The guarded script passed offline image and stock undo checks,
then fresh serial-bound Fastboot preflight. Fastboot accepted the 64 MiB
supplier image write to boot_a and one reboot. No other partition write or
slot switch was performed.

Candidate SHA-256:
20b76e5fee8e71ec703dfd37b6709c45f5b03c780a4bd40adb290ae998681fe5.
Trial receipt: logs/boot-a-supplier-trial-1791605323037986999.json.
Sending boot_a: OKAY 1.500 s; writing: OKAY 0.064 s; reboot: OKAY.

Passive USB observation completed. At first check no phone USB or ttyACM
console was present. Hardware boot and watchdog takeover remain unproven.
Stock boot_a restoration subsequently succeeded; see the completion record below.

Observation receipt: logs/lynx-usb-observation-1791605337236344040.json.
Elapsed seconds: 60.59. Events: [{"elapsed_seconds": 0.01, "usb": [], "serial_devices": []}].
No native USB console appeared during the observation. Hardware boot remains unproven.
The next action is to return physically to Fastboot for the authorized stock boot_a undo.
At the end of that observation, the trial image was still installed. It was subsequently replaced by the stock boot image as recorded below.

## Stock undo completed

The user confirmed continuation after physical Fastboot return. The phone
appeared as USB 0e8d:201c, bus 001 device 029. Initial guarded undo stopped at
read-only preflight because this reconnected USB node lacked Aria access;
no write was issued. Receipt: logs/boot-a-supplier-trial-1791605465181892297.json.
A per-device ACL was applied with pkexec setfacl -m u:aria:rw to
/dev/bus/usb/001/029. The guarded undo then passed fresh preflight.

Fastboot accepted the verified 64 MiB stock boot_a image: sending OKAY 1.498 s,
writing OKAY 0.067 s. Successful undo receipt:
logs/boot-a-supplier-trial-1791605504245693782.json.
Final read-only preflight passed:
logs/fastboot-preflight-1791605514489048808.json.
Product, bootloader, unlocked status, active slot A and partition sizes match
pre-trial values. No other partition was written; slot B was not switched or
written. No reboot was issued after stock undo. Lynx is left in Fastboot.

No Linux USB console appeared during this third trial's 60-second observation.
The phone's screen progression during this trial was not confirmed by the user.
Consequently a physical kernel boot, reset cause and watchdog takeover are
unproven. Fastboot acceptance is not byte-for-byte readback or proof that stock
recovery boots. Preserve the prepared images and logs; obtain stronger boot
observability before proposing further stored-image trials.
