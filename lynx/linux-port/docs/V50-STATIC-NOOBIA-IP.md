# Lynx V50 static Noobia address candidate — 2026-10-26

## Why this is needed

`/noobia/config/network-current.md` records `192.168.100.7` for Syra, while
the working V49 boot used that address for Lynx on 2026-10-25. On 2026-10-26,
two V49 reboots from Fastboot produced no authenticated SSH at `.7` or `.8`
within the first observation windows. A later LAN scan saw Dropbear briefly
at `.9`, but the endpoint stopped answering before its pinned Lynx host key
could be checked. This is evidence of an address or Wi-Fi problem, not proof
that the phone failed to boot. A low battery remains possible; Fastboot
exposes no usable battery percentage or voltage here.

The Council contact book lists Argus at `.105` and Nexus at `.106`.
`192.168.100.107` has no recorded owner and gave no ARP reply during a
read-only LAN check. It is proposed for Lynx. The router DHCP range has not
been verified, so a reservation or exclusion should be checked when network
administration is available.

## Offline image

`tools/build_v50_static_noobia_ip.py` derives V50 from the exact V49 image.
The sole functional change is in the rescue supplement's
`etc/lynx/wifi-runtime.sh`: after WPA association it configures
`192.168.100.107/24`, gateway `192.168.100.1`, and known Noobia DNS servers,
then starts rescue Dropbear bound to `.107`. Alpine's existing Wi-Fi service
adopts the associated interface and address, and its native Dropbear should
also bind to `.107`; this **requires a hardware trial**.

The independent validator found only the Wi-Fi runtime script changed in the
supplement and only its size/hash metadata changed in the primary ramdisk.
Kernel, command line, `/init`, other supplement members, and image tail match
V49. `sh -n` passed on the new script. No phone write occurred.

V50 candidate:
`linux-port/artifacts/static-noobia-ip-v50-offline/nord3-static-noobia-ip-v50-untested.img`
SHA-256 `6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59`.

Known working V49 rollback SHA-256:
`896aa4937b168090cd3c75d41995917dad05aedfbc7bf83790fe31342b061e0f`.
`python3 tools/lynx_boot_a_v50_trial.py --prepare` prints the exact commands
and checks both images and receipts without contacting Lynx. The guarded
flash tool permits **boot_a only**, requires a fresh charge confirmation,
and preserves slot B and recovery. Start
`python3 tools/observe_v49_first_boot.py --target v50` before any reboot.
If V50 fails and Fastboot is available, use the tool's `--restore-v49` path.

The initial flash hold was for an unknown battery level; Noob could not
confirm charge at that point.
An earlier Lynx hardware trial downloaded a boot image but the bootloader
rejected `fastboot boot` as `unknown command` (see
`RECOVERY-AND-FIRST-BOOT.md`), so a RAM-only V50 boot is unavailable.

## Controlled trial after explicit authorization

Noob then explicitly instructed Aria to flash despite the unknown battery
level. The trial tool recorded `battery_unknown_user_authorized=true` and a
fresh Fastboot preflight. It wrote **boot_a only** and Fastboot returned OKAY
for the 64 MiB transfer and write. Flash receipt:
`logs/v50-boot-a-trial-1793035445972539296/result.json`. The separate
reboot receipt is `logs/v50-boot-a-trial-1793035467294656587/result.json`.

The V50 observer found pinned rescue SSH at `192.168.100.107:22`; the rescue
boot log states `LYNX_STATIC_NOOBIA_IP ... address=192.168.100.107` at uptime
87 seconds. Alpine 3.24.2 then answered at `192.168.100.107:2222` and passed
three identity/health samples. Observer:
`logs/v50-first-boot-1793035460456770782/events.jsonl`. This proves one
successful V50 native Linux boot with the fixed address. Slot B, recovery,
bootloader, kernel and Alpine ext4 root were not changed by the flash.

At uptime 263 seconds Alpine reported battery **25%**, 24.9°C, CPU maximum
32.3°C, eight services running, and no ext4 errors. The MT6375 charger
reported `online=0`, `status=Not charging` while Lynx was cabled to Nexus.
Further display trials are held until external charging is established.
