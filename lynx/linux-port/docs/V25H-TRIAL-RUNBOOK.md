# V25h discovery trial

Status: **V25h written to `boot_a`; unplugged trial produced no network
contact, V19 restore pending Fastboot**. The guarded write
receipt is `logs/v25h-boot-a-trial-1792348863400477665.json`. The host did not
reboot Lynx and wrote no other partition or slot.

The V25g observer had no valid beacon and only probed the prior DHCP address.
Code review found that V25g's local Wi-Fi supervisor did not send the V19
discovery beacon. Therefore the V25g trial's lack of network contact could
include a changed DHCP lease. This is an observer blind spot, not proof that
V25g reached Wi-Fi or booted successfully.

V25h keeps V25g's exact kernel and init. The only supplemental member changed
is `etc/lynx/wifi-local-supervise.sh`, which now sends the existing pinned
`LYNX_HELLO` beacon when SSH is ready. Beacon failure does not prevent local
SSH. The image SHA-256 is
`e6afd7ae10f77d78939d4a6b011eaeca2c255c35642434040539913d9891bd5c`.
The local success and failure fixture, shell syntax, image package round trip,
observer identity parser and offline flasher checks passed. These checks do not
prove handset boot, Wi-Fi, health, or charging.

Fresh Fastboot preflight at `logs/fastboot-preflight-1792348651936872768.json`
matched exact serial, product, unlocked slot A and partition sizes. The
V25h-specific observer was armed before the write at
`logs/v25h-diagnostic-observer-1792348859569806838/result.json` and follows a
valid beacon to Lynx's actual IP. The guarded flasher rechecked identity and
image/restoration hashes before writing only `boot_a`.

For the physical trial, disconnect USB and boot normally. Do not attach a
charger during this unvalidated native boot. The candidate's early timer is
bounded to 180 seconds before health takes over. The observer must prove the
V25h `/init` hash, stock kernel, pinned SSH host key, offline charger and
health-ready marker. A black screen or orange warning alone is not proof.

On failure, save observer logs. Return to Fastboot without slot switching.
Arm a fresh pinned V19 collector, then run `python3 tools/restore_v19_boot_a.py
--flash --collector-receipt <fresh-result.json>` after its exact-identity
checks. The matching stock `boot_a` image remains at
`linux-port/artifacts/stock-cph2493-August-eu-ota/boot.img`; its hash and exact
Fastboot restoration command are in the write receipt. Do not retry V25h or
alter another partition on an unexpected identity, write response, recovery
screen, or warming handset.

The first unplugged physical trial showed the orange screen. The observer at
`logs/v25h-diagnostic-observer-1792348859569806838/result.json` recorded 118
unsuccessful pinned SSH probes and no valid beacon through the full bootstrap
plus early-health deadline. It was stopped after the evidence was saved.
This does not locate the failure, but the missing beacon is no longer caused by
the local supervisor lacking a beacon call: V25h includes that call and passed
its fake-network fixture. A fresh V19 recovery listener was armed at
`logs/wifi-v19-contact-1792349585406385976/result.json` before requesting
Fastboot and a guarded restore.
