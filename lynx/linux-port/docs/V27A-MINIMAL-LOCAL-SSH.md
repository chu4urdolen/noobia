# V27a minimal BusyBox self-boot diagnostic

Status: **offline-ready, not flashed**. Its image SHA-256 is
`db5381f525153971bc878109e67f47ad3256d6454d69eeab0802e3477e0024f4`.
The candidate derives from the exact V19 image that repeatedly reached
authenticated SSH. Only `/init`, its supplemental payload metadata, and one
existing `wifi-runtime.sh` member change. The stock kernel, boot command line,
other initramfs members, other supplemental members and partition length match
V19. The supplemental archive is 12,241,915 bytes, slightly smaller than V19.
The changed 4 KiB runs are limited to the boot header, primary ramdisk and
supplemental archive.

The V19 worker still loads storage, Wi-Fi, DHCP and Dropbear. V27a changes only
the supervisor's final decision: once it sees the exact V19 `ssh-ready`, PID,
interface and address markers, it sends three `LYNX_HELLO` beacons and returns
without requiring a Nexus acknowledgement. Its init starts an independent
180-second RAM timer after storage bootstrap; the timer requests power-off even
when SSH works. V27a has no automatic health startup, Alpine handoff or
persistent storage. It is a bounded diagnostic to isolate the failed V25d–h
self-boot changes. The exact packaged Wi-Fi script passed fake success and
failure scenarios at `linux-port/artifacts/v27a-wifi-fixture-1792350649240763450/result.json`.
Shell syntax, CPIO round trip, exact kernel/header preservation, image hash,
observer identity parser and offline flasher checks passed. None prove a phone
boot or real Wi-Fi.

Before a trial, save useful work from the live V19 RAM session. Arm
`python3 tools/observe_v25f_diagnostic.py --arm --seconds 900 --candidate v27a`,
return physically to Fastboot, and run the exact read-only identity preflight.
The guarded `tools/flash_v27a_boot_a.py --flash --observer-receipt <result.json>`
checks the stock undo, reviewed OTA, exact Fastboot identity and scoped
exception, then writes **only `boot_a`**. It never reboots. Disconnect USB
before booting V27a and watch the observer for pinned SSH, actual beacon IP,
kernel/init hash and offline charger. A positive observer result is only early
BusyBox SSH proof; the timer still powers off. Do not infer health or Alpine.

After the diagnostic, return to Fastboot without slot switching. Arm a fresh
V19 pinned collector, then run `tools/restore_v19_boot_a.py --flash
--collector-receipt <fresh-result.json>`. The exact stock `boot_a` remains at
`linux-port/artifacts/stock-cph2493-August-eu-ota/boot.img`. Stop on unexpected
identity, write response, recovery mode, or warming. Preserve observer and
pstore/expdb receipts before another trial.
