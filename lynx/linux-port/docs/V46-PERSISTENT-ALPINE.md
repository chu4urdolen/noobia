# V46 conditional startup timer cancellation

V45 proved autonomous BusyBox-to-Alpine handoff on Lynx. Its boot ID
`d91fa1cc-aa20-49a8-a777-f03a72b14fc9` reached Wi-Fi, health, and
checksummed `HANDOFF_BEGIN`; pinned SSH independently verified Alpine 3.24.2,
OpenRC PID 1, health service, persistent ext4 root, and no host arming. It
remained reachable through uptime 428 before contact ended at its intentional
420-second startup timer boundary.

V46 derives from exact V45 and changes only primary `/init`. After the
same three consecutive passing health checks and `HANDOFF_BEGIN` record,
it loads the already packaged local OpenRC helper, stops and reaps the
startup timer, records `TIMER_CANCELLED` in the checksummed boot log, and
calls the same helper. If timer cancellation or its diagnostic record fails,
it requests power-off. If the handoff helper returns, the parent continues
the existing health-check loop and powers off at uptime 300. The independent
battery and thermal watchers, charger guard, and OpenRC health service remain
unchanged. A successful handoff has no outer startup deadline; this is the
first candidate for a self-booting persistent Alpine session. Charging while
running is still not enabled by this candidate.

The stock kernel, command line, supplementary payload, local handoff helper,
all other primary ramdisk members, and V33/V19 rollback images remain exact.
Private image:
`artifacts/persistent-alpine-v46-offline/nord3-persistent-alpine-v46-untested.img`,
SHA-256 `6c487df1c16af1717e045167c165271065e9060c5a02b16b8e1b3ce3eca28f91`.
The builder and independent validator receipts are beside it. Validation
checked the exact V45 parent, two-site `/init` delta, BusyBox syntax,
unchanged supplement and stock kernel, rollback hashes, and pinned AVB
behavior in unlocked and locked cases. The guarded `boot_a` trial
`--prepare` passed. A local parser fixture accepted checksummed
`TIMER_CANCELLED` as a nonterminal stage.

**V46 has not been flashed or booted.** After preparation, read-only PL/LK
was captured and exact V33 restored **only to `boot_a`**; pinned Wi-Fi SSH,
V31 RAM health, guarded handoff, and Alpine/OpenRC PID 1 passed:
`logs/v33-alpine-pid1-verification-1792680518669188817/result.json`.
The V46 observer dry run correctly rejected live V33 as V46 while detecting
Alpine PID 1: `logs/v46-health-window-1792680522964230929/result.json`.
A controlled
V46 trial needs fresh Fastboot preflight and pinned collector before flashing
**only `boot_a`**, a separate reboot, prompt USB unplug, exact `/init` and
same-boot Alpine verification, `TIMER_CANCELLED` record, and observation
beyond V45's 428-second shutdown boundary. Preserve slot B, bootloader,
recovery, and all other partitions. Keep the exact V33 restoration ready.
