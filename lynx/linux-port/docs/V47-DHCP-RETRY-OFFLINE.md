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

**V47 has not been flashed or tested on hardware.** V46 remains the working
`boot_a` image. The retry addresses only one observed failure class. A
controlled hardware trial would need a fresh Fastboot recovery preflight,
the exact V46 image ready for restoration, a pinned SSH observer, and a
safe cable/power procedure. Keep the current V46/Alpine SSH session for
live userland work until that trial is worth interrupting it.

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
