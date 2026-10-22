# V43 three-sample health observation — offline candidate

Three checksum-verified V42 boots reached `HEALTH_READY`, then wrote
`HEALTH_FAIL_POSTCHECK` within one second. The parent requested power-off
after a single rejected supervisor `--once` sample. The already running
independent supervisor instead requires **three consecutive failures** before
requesting power-off. The specific failed inner condition is not yet known.

V43 derives from the exact V42 image. Only primary `/init` changes. In the
post-readiness observation window, a passing `--once` check resets the parent
failure counter; a rejected check increments it and logs the count. The parent
requests power-off and saves `HEALTH_FAIL_POSTCHECK` only after three
consecutive rejections, sampled five seconds apart. The independent supervisor,
thermal and battery watchers, charger guard, 420-second outer power-off timer,
and final power-off at uptime 300 remain. The stock kernel, command line,
health child, and entire supplementary payload remain byte-for-byte V42.
There is no Alpine handoff in this candidate.

Private image:
`artifacts/health-tolerance-v43-offline/nord3-health-tolerance-v43-untested.img`,
SHA-256 `4c088d2b4aca070510291322b9a809947100cecf0909bc458727914f5afbd875`.
The builder and independent validator receipts are beside it. Validation
checked the exact two-site `/init` delta, BusyBox syntax, unchanged supplement,
stock kernel, V33/V19 rollback hashes, and pinned AVB model in unlocked and
locked cases. The guarded trial `--prepare` passed. A one-second pinned
collector dry run against live V33 captured one sample and correctly rejected
it as V43: `logs/v43-health-window-1792667833465627951/result.json`.

## Hardware trial, 2026-10-22

V43 was flashed **only to `boot_a`** after offline validation and a fresh
Fastboot preflight. The guarded flash and separate reboot receipts are
`logs/v43-boot-a-trial-1792673516525528533/result.json` and
`logs/v43-boot-a-trial-1792673522465379649/result.json`. The collector was
already running and the USB cable was removed after the reboot request.

Pinned Wi-Fi SSH verified the exact V43 `/init` hash on boot ID
`bb9766d9-717b-47a6-a519-b16fb956118e`. The child reached
`HEALTH_READY` at uptime 208.10 seconds. The last complete SSH sample was
at uptime 303.11 seconds, beyond V42's immediate shutdown at 210–211 and
V43's planned observation limit of 300. The next SSH sample timed out;
the recovered checksummed persistent record confirms `END` at uptime 304.
The last postcheck was
`LYNX_HEALTH_OK` with 28.5 °C battery and 36.5 °C hottest sampled thermal
sensor. There were 159 complete SSH samples, plus one timeout, in
`logs/v43-health-window-1792673512487557123/`.

The read-only PL/LK log was saved at `logs/pllk-1792674120413073823.json`.
Exact V33 was restored **only to `boot_a`**, without an implicit reboot:
`logs/v34-boot-a-trial-1792674123467242532/result.json`. A separate
Fastboot reboot, pinned Wi-Fi SSH, V31 RAM health, guarded handoff, and
Alpine/OpenRC PID 1 all passed:
`logs/v33-alpine-pid1-verification-1792674286205723296/result.json`.
The V43 boot-ID record, including the `END` stage, was independently read
and checksum verified at
`logs/v38-persistent-capture-1792674289456124190/result.json`.
**V33 is installed and Alpine is running.** V43's bounded health observation
passed; autonomous Alpine handoff remains the next unproved step. Slot B,
bootloader, recovery, and all other partitions were preserved.
