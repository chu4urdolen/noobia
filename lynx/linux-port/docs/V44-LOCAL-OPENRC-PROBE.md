# V44 bounded local Alpine/OpenRC handoff probe

V43 booted native BusyBox, reached Wi-Fi SSH, started the V31 health watchers,
passed health checks through uptime 303, and recorded a verified `END` at 304.
V33 separately proved that the exact persistent Alpine 3.24.2 root can run
OpenRC as PID 1 with Wi-Fi SSH and health, but V33 still needs host arming.
V44 joins those two proven portions in one **bounded diagnostic boot**.

V44 derives from exact V43 and changes only primary `/init`. The kernel,
command line, every other ramdisk member, supplementary payload, local
authority OpenRC helper, root identity guards, health watchers, charger
guard, and 420-second outer power-off timer remain byte-for-byte unchanged.
The new tail waits for three consecutive passing health supervisor checks,
records `HANDOFF_BEGIN` on the verified ext4 boot log, and calls the already
packaged local authority OpenRC handoff. If that handoff returns, it records
`HANDOFF_REFUSED` when possible and continues monitored BusyBox until the
planned 300-second end. Three consecutive health failures still request
power-off. If OpenRC runs, the inherited outer timer deliberately powers
off the trial at about uptime 428; this is **not** a daily boot image.

The AVB-covered primary ramdisk had only 22 compressed bytes free. The build
removes 12 complete shell-comment lines from `/init` to fit the new tail;
all executable lines before the health-ready branch remain identical to V43
except the two new boot-stage names in the diagnostic allowlist. The builder
and independent validator check this exact transformation and BusyBox shell
syntax. The stock kernel and complete V43 supplement are unchanged.

Private image:
`artifacts/local-openrc-probe-v44-offline/nord3-local-openrc-probe-v44-untested.img`,
SHA-256 `c709158f962853ed86b6605ab2b3bb8866cae93518e3c762a239ebae0b6b3358`.
Build and validation receipts are beside it. Validation covers exact V43,
V33/V19 rollback hashes, local helper, image scope, and the pinned AVB model
in unlocked and locked cases. The guarded `boot_a` trial `--prepare` passed.
A three-second read-only collector dry run on live V33 Alpine correctly saw
Alpine PID 1 but rejected V33 as V44:
`logs/v44-health-window-1792674657320489839/result.json`.

## First hardware trial, 2026-10-22

V44 was flashed **only to `boot_a`** after fresh Fastboot preflight, then
rebooted separately. The guarded flash and reboot receipts are
`logs/v44-boot-a-trial-1792676567481849323/result.json` and
`logs/v44-boot-a-trial-1792676577664867780/result.json`. The prestarted
pinned collector saw no SSH candidate over 456 seconds:
`logs/v44-health-window-1792676563381362480/result.json`. The host kernel
recorded USB disconnect at the Fastboot reboot and no reappearance until
Lynx returned to Fastboot about six minutes later.

Read-only PL/LK was saved at `logs/pllk-1792677043594151938.json`, then exact
V33 was restored **only to `boot_a`** with no implicit reboot:
`logs/v34-boot-a-trial-1792677046147348297/result.json`. Its subsequent
unplugged boot reached pinned Wi-Fi SSH, passed V31 RAM health, and ran
Alpine/OpenRC as PID 1:
`logs/v33-alpine-pid1-verification-1792677239930378372/result.json`.

The V33 Alpine boot read and checksum-verified V44's persistent stage record
at `logs/v38-persistent-capture-1792677243171127255/result.json`. V44 boot ID
`30262823-2e51-441b-a9f3-1ceec5ff7a0a` recorded `START` at uptime 8 and
`WIFI_FAILED` at uptime 98. There is no `WIFI_READY`, health, or handoff
stage. This localizes the first trial to the Wi-Fi worker path; it provides
**no hardware evidence about the new OpenRC handoff branch**. The precise
Wi-Fi failure condition is unknown because the current persistent format
stores stage names but not the worker's RAM log. A repeat of the exact image
could distinguish a transient Wi-Fi failure, but a repeated failure would
need richer persistent Wi-Fi diagnostics. V33 Alpine is installed and
running. Slot B, bootloader, recovery, and all other partitions were
preserved.
