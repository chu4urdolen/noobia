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
Its retained token `69adf9d14707d848063b861b8f248748` belongs to an
**older experiment**, documented before this trial. Exact V46's ramdisk token
is `c4086e17473b3a2b59f233cfb0d98438`. A corrected local provenance
check explicitly excludes the old pstore trace from V46:
`logs/pstore-retained-token-1792697932761260892.json`. The earlier
`logs/pstore-previous-boot-1792683031840922664.json` misattributed that old
trace and is superseded. The PL/LK snapshot covers the later Fastboot entry.
The first V46 attempt's stop point remains **unknown**; absence of SSH and a
persistent stage record does not locate it.

The second trial below established successful autonomous Alpine. The first
trial is evidence of startup variability, not of a particular UFS failure.

## Second hardware trial, 2026-10-22

After exact V33 recovery, a second fresh Fastboot preflight passed and the
same V46 image was written **only to `boot_a`**. A separate Fastboot reboot
and immediate USB unplug started boot ID
`917238d2-f2c3-479b-9ded-6f677c474763`:
`logs/v46-boot-a-trial-1792697098131135652/result.json` and
`logs/v46-boot-a-trial-1792697105660523171/result.json`.
The pinned Wi-Fi collector verified exact V46 `/init`. The checksum-verified
persistent stage record has `WIFI_READY` at uptime 99, `HEALTH_READY` at 211,
`HANDOFF_BEGIN` and `TIMER_CANCELLED` at 221:
`logs/v46-same-boot-stage-1792697419990383186/result.json`.
An independent pinned SSH check verified Alpine 3.24.2/OpenRC as PID 1,
persistent ext4 root, running health service, Wi-Fi SSH, Python, and Git,
with no host arming:
`logs/v46-autonomous-alpine-verification-1792697396638346147/result.json`.
Alpine's own OpenRC Dropbear service was independently reached over pinned
Wi-Fi SSH on port 2222, with the same boot ID and Alpine root:
`logs/v46-alpine-native-ssh-1792697679963651084/result.json`. Rescue SSH
remains on port 22.
The bounded observer completed 234 samples: 233 complete SSH snapshots with
the same boot ID, one timeout followed by recovery, and Alpine PID 1 from
uptime 222.83 through the final uptime 672.51. This is beyond V45's
uptime-428 contact loss at the startup timer boundary:
`logs/v46-health-window-1792697094431894340/result.json`. A second
independent health/Alpine verifier passed after uptime 500:
`logs/v46-autonomous-alpine-verification-1792697630182923996/result.json`.
An offline verifier rechecked every complete sample hash, same boot ID,
monotonic uptime, and Alpine at uptime 672.51:
`logs/v46-window-verification-1792697834605535104.json`.

**V46 is installed on `boot_a` and Alpine is running autonomously.** This
proves the startup timer was canceled and no immediate fallback stopped the
session. It does not yet prove a cold boot after full power-off, reliable UFS
startup on every attempt, sustained charging, or operation without the
independent battery and thermal guards. Exact V33 and V19 rollback images
remain available; slot B, bootloader, recovery, and other partitions were
preserved.

## Repeatable guarded procedure

The private image and logs stay under `/noobia/lynx`; never use a similarly
named image for another model. From `/noobia/lynx`, with Lynx in Fastboot on
USB, run the offline validator and `--prepare`, then start the pinned V46
collector. Pass its printed receipt to `--flash-v46`; after a successful
`v46-flashed-no-reboot` receipt, pass that receipt to
`--reboot-after-v46`. **Unplug USB immediately after the reboot command**;
the existing charger guard can shut down an attached trial. The guarded trial
performs fresh identity, slot, and partition-size preflight at both steps.
Verify exact `/init`, same-boot Alpine/OpenRC, and the checksummed
`TIMER_CANCELLED` record with `verify_persistent_alpine_v46.py` and
`capture_v46_same_boot_trace.py`. Keep the collector running beyond uptime
428. These commands write only `boot_a` at the flash step; the observer and
verifiers are read-only.

If V46 does not reach pinned SSH, return Lynx physically to Fastboot on USB,
capture `sudo -n python3 tools/lynx_pllk_log.py --connect`, and restore exact
V33 with `sudo -n python3 tools/lynx_boot_a_v34_trial.py --restore-v33`.
That command does **not** reboot. Start a fresh pinned V33 contact collector,
run fresh Fastboot preflight, reboot, and unplug immediately. Once Wi-Fi SSH
appears, run the V31 RAM health trial, guarded V33 OpenRC arm, and Alpine PID 1
verifier before treating recovery as complete. The V33 contact collector saves
read-only pstore. `analyze_retained_pstore.py` checks its retained token against
the exact candidate image before any boot attribution; a different or reused
static token cannot prove which recent boot produced the trace.
