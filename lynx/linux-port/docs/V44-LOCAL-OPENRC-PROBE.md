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

**V44 has not been flashed or booted.** V33 is installed and Alpine/OpenRC
last verified running. A controlled trial needs a fresh pinned collector
started before a fresh Fastboot preflight, a guarded flash of **only `boot_a`**,
a separate reboot, and immediate USB unplug. Observe the exact V44 `/init`
before the handoff, then the same boot ID with OpenRC PID 1, persistent ext4
root, Wi-Fi SSH, and passing health. The bounded shutdown or failure should
be followed by exact V33 `boot_a` restoration, Alpine verification, and
checksummed persistent-stage retrieval. Preserve slot B, bootloader,
recovery, and all other partitions.
