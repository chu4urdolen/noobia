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

After preparation, read-only PL/LK
was captured and exact V33 restored **only to `boot_a`**; pinned Wi-Fi SSH,
V31 RAM health, guarded handoff, and Alpine/OpenRC PID 1 passed:
`logs/v33-alpine-pid1-verification-1792680518669188817/result.json`.
The V46 observer dry run correctly rejected live V33 as V46 while detecting
Alpine PID 1: `logs/v46-health-window-1792680522964230929/result.json`.

## First hardware trial, 2026-10-22

Fresh Fastboot preflight passed; the guarded trial wrote V46 **only to
`boot_a`** and rebooted separately:
`logs/v46-boot-a-trial-1792682295917618952/result.json` and
`logs/v46-boot-a-trial-1792682302328970253/result.json`. USB was unplugged
for boot. The pinned observer saw no V46 SSH contact in the first five
minutes. After Lynx was returned to Fastboot, read-only PL/LK was saved as
`logs/pllk-1792682626286180183.json`. Exact V33 was restored **only to
`boot_a`**: `logs/v34-boot-a-trial-1792682628744993536/result.json`.
The unplugged V33 reboot reached pinned SSH, passed V31 RAM health and guarded
handoff, and independently verified Alpine/OpenRC PID 1:
`logs/v33-alpine-pid1-verification-1792682811956277416/result.json`.
The V46 observer was stopped after it saw V33 Alpine; it never matched V46:
`logs/v46-health-window-1792682292434727726/result.json`.

The checksum-verified persistent log capture
`logs/v38-persistent-capture-1792682815070129601/result.json` contained the
same twelve boot IDs as the previous capture, with **no new V46 record**.
The pinned V33 contact also saved read-only pstore immediately after recovery:
`logs/dynamic-pinned-contact-1792682635409608967/pstore-and-boot.raw`.
Its **previous-boot** token `69adf9d14707d848063b861b8f248748`
differs from the current V33 token. Checksum-valid pmsg stages show PID 1's
early guard at uptime 0, UFS probe preparation at uptime 3, then UFS probe
begin. The corresponding console ends at tracepoint 4 of
`ufs_mtk_setup_ref_clk` (`+0xa0`) and has no probe-return marker:
`logs/pstore-previous-boot-1792683031840922664.json`. That is the last
visible point, **not** an instruction-level proof of the hang location. It
establishes that V46 reached the stock kernel and storage initialization but
did not reach its later Wi-Fi or timer-cancellation path. The same early UFS
reference-clock problem was observed in older bounded trials; the V46 primary
`/init` change is downstream of it. The PL/LK snapshot covers the later
Fastboot entry and does not refine this point.

Do not describe this trial as a successful autonomous or persistent boot.
Preserve V33 as the working image until a further controlled trial or a
specific early UFS remedy is ready.
