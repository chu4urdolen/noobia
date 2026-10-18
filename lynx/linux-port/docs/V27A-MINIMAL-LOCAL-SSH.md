# V27a minimal BusyBox self-boot diagnostic

Status: **timed repeat proved autonomous BusyBox Wi-Fi and authenticated SSH;
V27a remains a bounded diagnostic with a pending V19 restoration**. Its image SHA-256 is
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

The supervised V27a trial wrote only `boot_a` after exact Fastboot identity
verification; receipt: `logs/v27a-boot-a-trial-1792351913669138575.json`.
The host issued no reboot. The 900-second observer
`logs/v27a-diagnostic-observer-1792351911626040244/result.json` ended at
`deadline-without-health-proof` with 149 unsuccessful pinned SSH probes and no
valid beacon. Fastboot was still connected at least a minute after flashing
and had disappeared by the next check near the observer deadline. No USB or
screen trace established when physical boot started, so the observer may have
covered too little native runtime to judge V27a. Do not count this as a V27a
boot failure. The guarded
V19 restoration at `logs/v19-rescue-boot-a-1792353076061538334.json` verified
the same identity and wrote only `boot_a`; the host again issued no reboot.
A fresh V19 contact collector at
`logs/wifi-v19-contact-1792353073291818117/result.json` verified a valid
beacon and pinned SSH. The passive USB record at
`logs/v19-rescue-usb-departure-1792353076061538334.json` places the first
beacon 117.709 seconds after Fastboot USB departure. The autonomous RAM health
stage then passed at `logs/autonomous-health-ram-trial-1792353506105490795/result.json`,
and the Alpine development checkpoint was restored in RAM at
`logs/alpine-checkpoint-live-restore-1792353532587655041/result.json`.

For any repeat of V27a, start both the network observer and passive USB
observer while Fastboot is connected. Begin the native boot window at the
recorded USB departure, not at the time the network observer was armed. Allow
at least 420 seconds after departure before treating missing SSH as a negative
result; the verified V19 rescue took 117.709 seconds to beacon. Keep the
observer active long enough to cover human delay before unplugging.

The timed repeat used the exact same V27a image. Its guarded `boot_a` write
receipt is `logs/v27a-boot-a-trial-1792353870113193430.json`; no other
partition was touched and the host did not reboot Lynx. Passive USB recording
at `logs/v27a-repeat-usb-1792353858696.json` captured Fastboot departure at
wall-clock ns `1792353979029038472`. The image-aware observer at
`logs/v27a-diagnostic-observer-1792353867572216336/result.json` received a
valid beacon 119.677 seconds later and verified pinned SSH 119.929 seconds
after departure. It identified the V27a `/init` hash and captured native
kernel diagnostics. At phone uptime 93.63 seconds, the live boot log recorded
`MINIMAL_LOCAL_SSH_READY interface=wlan0 address=192.168.100.7` and
`MINIMAL_LOCAL_SSH_RETURNED`; the Wi-Fi worker returned 0 and the Nexus
`host-confirmed` marker was absent. A read-only copy of this proof is
`logs/v27a-diagnostic-observer-1792353867572216336/local-success-readonly.txt`.
This establishes local Wi-Fi/SSH readiness without a Nexus acknowledgement.
It does not establish automatic health, safe charging, Alpine handoff or
persistent storage. The independent V27a power-off timer remains active.
