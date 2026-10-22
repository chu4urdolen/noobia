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

## Hardware trial, 2026-10-22

V45 was flashed **only to `boot_a`** after a fresh Fastboot preflight, then
rebooted separately with the pinned collector already running. Receipts:
`logs/v45-boot-a-trial-1792678296156203144/result.json` and
`logs/v45-boot-a-trial-1792678305143540522/result.json`.

Pinned SSH verified the exact V45 `/init` on boot ID
`d91fa1cc-aa20-49a8-a777-f03a72b14fc9`. The checksummed persistent log
records `WIFI_READY` at uptime 96, `HEALTH_BEGIN` at 191,
`HEALTH_READY` at 208, and `HANDOFF_BEGIN` at 218:
`logs/v45-live-stage-1792678624278192962/result.json`.
The local authority guard passed, and independent SSH verification proved
Alpine 3.24.2/OpenRC as PID 1, persistent ext4 root, running health service,
working Wi-Fi SSH, Python, and Git, with no host arming marker:
`logs/v45-autonomous-alpine-verification-1792678596444971030/result.json`.
The pinned collector retained 244 complete samples and observed Alpine
through uptime 428.30, followed by SSH loss at the expected 420-second
outer timer boundary (started near uptime 8):
`logs/v45-health-window-1792678292672890646/result.json`.

**Recovery is pending.** V45 is the last image written to `boot_a`.
After Lynx returns to Fastboot on USB, capture read-only PL/LK, restore exact
V33 **only to `boot_a`**, boot unplugged, and verify Alpine. The timer
boundary is consistent with planned shutdown, but its exact final command
was not captured before SSH loss. V45 proves autonomous local handoff in a
bounded trial; a persistent daily boot still needs to cancel the outer timer
only after this health and handoff proof. Preserve slot B, bootloader,
recovery, and all other partitions.
