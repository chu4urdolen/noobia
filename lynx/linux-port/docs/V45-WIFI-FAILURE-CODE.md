# V45 bounded handoff probe with Wi-Fi failure code

V44's first boot recorded `START` and `WIFI_FAILED` at uptime 98, before
health or OpenRC, but its persistent stage log did not retain the Wi-Fi
worker's numeric result. V45 derives from exact V44. It leaves the stock
kernel, command line, complete supplementary payload, local OpenRC helper,
watchers, and 420-second safety timer unchanged. Only primary `/init` changes:
on a Wi-Fi failure it records `WIFI_FAILED` and then either the numeric
`WIFI_ERR_<code>` from `/run/lynx/worker-result` (if a bounded numeric code
exists) or `WIFI_NO_RESULT`. The worker's existing return codes distinguish
storage, radio, interface, WPA, DHCP, and SSH stages. Successful Wi-Fi,
delayed health, and the three-pass local OpenRC handoff are identical to V44.
The checksummed persistent parser accepts the new stage names.

Private image:
`artifacts/wifi-failure-code-v45-offline/nord3-wifi-failure-code-v45-untested.img`,
SHA-256 `228b290e478649b7b7c48a865365771b73dbac73aaac361f73a245ddff24ca87`.
The builder and independent validator receipts are beside it. Validation
checked exact V44, the two-site primary `/init` change, unchanged supplement
and stock kernel, V33/V19 rollback hashes, BusyBox syntax, and pinned AVB
behavior in unlocked and locked cases. The guarded `boot_a` trial `--prepare`
passed. The read-only collector dry run on live V33 Alpine saw Alpine PID 1
but correctly rejected V33 as V45:
`logs/v45-health-window-1792677524606293397/result.json`. A local parser
fixture accepted a checksummed `WIFI_ERR_143` record.

**V45 has not been flashed or booted.** V33 Alpine is installed and verified.
For a controlled trial, start the pinned V45 collector first, then fresh
Fastboot preflight, flash **only `boot_a`**, reboot separately and promptly
unplug USB. If Wi-Fi works, verify exact V45 `/init` and Alpine/OpenRC on the
same boot ID. If it fails, restore V33 and retrieve the checksummed worker
code before changing Wi-Fi. Preserve slot B, bootloader, recovery, and all
other partitions. The candidate remains a bounded diagnostic, not a daily
boot image.
