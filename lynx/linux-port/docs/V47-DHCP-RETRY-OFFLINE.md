# Lynx V47 bounded DHCP retry candidate

Lynx's checksummed persistent V46 boot records include `WIFI_ERR_144` on
several boots, including boot `d2867273-e18d-4c21-8a63-b71c53041044` at
uptime 105 seconds. Code review maps 144 to the BusyBox `udhcpc` command in
the initramfs Wi-Fi worker. That command currently makes one bounded DHCP
attempt and returns a boot failure if the attempt fails. The records do not
show whether the DHCP server, radio, hook, or network timing caused the
failure; a separate boot reached `WIFI_READY` and then stopped later.

`tools/build_wifi_dhcp_retry_v47.py` starts from the exact working V46 image
and changes only `etc/lynx/wifi-runtime.sh` in its supplementary payload.
The worker now makes at most three bounded DHCP attempts, with a three-second
pause after each failed attempt except the last. It retains return code 144
after all three fail and logs each attempt in the early boot log. The V46
primary init, stock kernel, command line, early boot timer, health guards,
and Alpine ext4 root are unchanged. The primary ramdisk changes only its
supplement length and checksum fields to match the new payload.

The offline image is
`artifacts/wifi-dhcp-retry-v47-offline/nord3-wifi-dhcp-retry-v47-untested.img`,
SHA-256 `c969e1938b051ab03b49ad4f2260e900e9e336997d1026ca00c3a493dedde066`.
`tools/validate_wifi_dhcp_retry_v47.py` independently checked exact V46,
V33 rollback and stock kernel hashes, primary and supplementary member
scope, shell syntax, image roundtrip, unchanged image tail and AVB model
behavior with the bootloader unlocked and locked. The extracted retry block
passed fixtures for success on attempts one, two and three and failure after
all three. Receipts:

- `artifacts/wifi-dhcp-retry-v47-offline/build-result.json`
- `artifacts/wifi-dhcp-retry-v47-offline/validation.json`
- `artifacts/wifi-dhcp-retry-v47-offline/dhcp-fixtures.json`

Before the hardware trial described below, V47 had not been flashed or
tested on Lynx. The retry addresses only one observed failure class. A
controlled trial required a fresh Fastboot recovery preflight, the exact
V46 image ready for restoration, and a pinned SSH observer.

`tools/lynx_boot_a_v47_trial.py --prepare` now checks the exact V47, working
V46, V33 and V19 images, offline validation, retry fixtures, and pinned
Fastboot binary without contacting the phone. It prints the exact `boot_a`
flash and V46 restoration commands. Its separate flash and reboot modes
require a fresh observer receipt and a fresh Fastboot identity/partition
preflight; no mode switches slot or touches another partition. The
`--restore-v46` mode is available if a future trial fails and Lynx returns
to Fastboot, but restoration is never automatic after an unexpected result.

`tools/capture_v47_health_window.py` was run for eight seconds against the
currently working V46 session as a read-only negative control. Three pinned
SSH samples verified V46 `/init` and Alpine PID 1 while correctly rejecting
V47's changed Wi-Fi script hash:
`logs/v47-health-window-1792785160997090342/result.json`.

## Controlled hardware trial, 2026-10-23

After Noob authorized the trial and Lynx appeared in Fastboot on USB, the
fixed read-only Fastboot preflight matched the expected serial, product,
unlocked state, slot A, bootloader, partition sizes and download limit:
`logs/fastboot-preflight-1792785302313036393.json`. The USB device needed
a scoped current-device ACL so the pinned Fastboot executable could open it.
The V47 observer was started before the write. Guarded commands then wrote
**only `boot_a`** and separately requested reboot:

- `logs/v47-boot-a-trial-1792785312151881578/result.json`
- `logs/v47-boot-a-trial-1792785319356119019/result.json`

The pinned observer found new boot ID
`9054078d-aafa-4abf-9600-5c70f8234360`, exact V46-derived `/init`, and
the exact V47 Wi-Fi script on the phone. Its early boot log shows DHCP
success on **attempt one**; this trial therefore does not exercise retry
after a failed DHCP attempt. The checksummed stage record includes
`WIFI_READY`, `HEALTH_READY`, `HANDOFF_BEGIN`, and `TIMER_CANCELLED`.
Alpine 3.24.2/OpenRC became PID 1, and pinned Alpine SSH on port 2222
verified ext4 root; health, reserve, local logs, Wi-Fi, SSH, maintenance,
time sync and power-history services; NTP synchronization; and the current
boot's private power-history entry. The prior V46 boot's power entries,
service log marker, and early boot log survived:
`logs/v47-live-verify-1792785655574139377/result.json`.

The observer collected 163 same-boot samples and was stopped after Alpine
remained healthy through uptime 465 seconds, beyond the old 420-second
outer-timer boundary. The independently checked window receipt is
`logs/v47-window-verification-1792785806022669372.json`.
Pinned Alpine SSH and the full service/bootdiag proof still passed after
that boundary:
`logs/v47-live-verify-1792785810920985149/result.json`.
At the last sample the gauge reported 84%, +144 mA, and 26.2°C.

This establishes one autonomous V47 boot and sustained Alpine operation,
including restart persistence of the local logger, time-sync service, and
power history. It does **not** prove that a second or third DHCP attempt
works on this hardware, or that every boot succeeds. V46 is retained locally
as the exact `boot_a` restoration image. Slot B, bootloader, vendor boot,
recovery-related partitions and Alpine ext4 root were not flashed or changed
by this trial.
