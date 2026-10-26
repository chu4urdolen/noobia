# Current Lynx handoff state

## Latest — 2026-10-26 V50 boots Alpine at static `.107`; charging absent

Noob explicitly authorized V50 flashing despite an unknown battery level.
The guarded tool wrote boot_a only after Fastboot and rollback preflights.
Pinned rescue SSH answered at `192.168.100.107:22`, then Alpine 3.24.2
answered at `:2222` and passed three health observations. Battery was 25%,
24.9°C; the MT6375 charger reported `online=0`, `Not charging` on the Nexus
cable. The display trial is held while a working power source is arranged.
See `V50-STATIC-NOOBIA-IP.md` and
`logs/v50-first-boot-1793035460456770782/events.jsonl`.

## Earlier — 2026-10-26 V50 static `.107` prepared offline

The Noobia address book records `.7` for Syra. Lynx had also used `.7` on
V49, creating an address conflict. Two V49 boots on 2026-10-26 did not yield
authenticated SSH at the old `.7`/`.8` addresses. A brief Dropbear response
at `.9` was not pinned-identity verified. Battery state is unknown because
Fastboot provides no usable reading; Noob reported battery trouble.
V50 was built and independently validated offline to put both rescue and
Alpine handoff at the proposed free `.107`. V49 rollback was pinned. At this
point no V50 flash had occurred. Noob later authorized the controlled flash
recorded above. See `V50-STATIC-NOOBIA-IP.md`.

## Latest — 2026-10-25 first visible Lynx display output

Noob watched the announced 12-second V49 atomic DRM + brightness 400 trial
and reported that Lynx's screen worked. The trial used the connected
1240×2772 DSI mode, imported DMA-BUF XRGB8888 primary plane, and restored
brightness zero afterward. Alpine stayed on the same boot and health passed.
Evidence: `logs/v49-dmabuf-trial-1792964620246017995/`. The driver still
emitted idle-manager, ESD-read, and doze/shutdown warnings; no CMDQ timeout
or reboot was observed. The pattern was transient, and no display service or
GUI is installed. See `V49-IOMMU-BEFORE-CMDQ.md` for the exact sequence.
The matching display modules and bounded replay commands are now stored on
Alpine; their preparation and test-only checks passed without a visual trial.
Receipt: `logs/v49-display-bundle-1792964869103429928/`. Startup is not
enabled; the phone-side visual command still needs an announced observation.

## Earlier — 2026-10-25 V49 boots, touch coordinates verified, legacy display times out

V49 was flashed to boot_a only after Fastboot identity and partition checks;
V48 rollback remains ready. V49 rescue and Alpine SSH returned on boot
`38795684-219b-4b82-9b36-2b3001fc02a6`. GCE now has an IOMMU group, and
the boot log confirms stock `mtk_iommu.ko` loaded before CMDQ. Alpine health
passed three observer samples. A bounded ten-second DRM draw still hit a
real CMDQ timeout at event 644 (`EVENT_STREAM_BLOCK`), so display output
remains unverified and no repeat draw should be made without a new fix.
The touchscreen driver registered `/dev/input/event0`, and Noob's taps
produced 12 press/release pairs with X/Y coordinates. Details and receipts:
`V49-IOMMU-BEFORE-CMDQ.md`.

## Latest — 2026-10-25 V49 IOMMU boot candidate prepared offline

Noob confirmed Lynx stayed black during the 15-second V48 color-bar test.
The test returned exit 0 but kernel CMDQ error interrupts with `err:-22`
occurred. The original trial parser missed them; it now detects them.
Source review and read-only sysfs suggest a missing IOMMU domain for GCE.
The stock `mtk_iommu.ko` is absent from V48's boot module order, although
stock `modules.load` places it before CMDQ. See `V49-IOMMU-BEFORE-CMDQ.md`.

An offline V49 candidate adds only this exact stock module and loads it
before CMDQ. Its builder, independent validator, and boot_a-only trial tool
passed offline checks. SHA-256 is
`896aa4937b168090cd3c75d41995917dad05aedfbc7bf83790fe31342b061e0f`.
The known-working V48 image is verified and ready for Fastboot restoration.
This was the offline state before the controlled boot trial documented above.

## Latest — 2026-10-25 V48 display command completes with SCMI chain

The earlier MMInfra BUG exposed a missing module in our display bootstrap:
the matching stock `modules.load` puts `mtk-mbox-mailbox.ko` immediately
before `tinysys-scmi.ko`. Read-only sysfs showed the mailbox and ARM SCMI
platform devices unbound. On recovered V48 boot
`89ee3cfd-fb7c-4c66-94ec-7ae1a12d6f73`, guarded RAM-only supplier
probes loaded mailbox, tinysys SCMI, then MMInfra debug separately. The
mailbox bound, SCMI firmware reported protocol v1.0, tinysys device
`scmi_dev.1` bound, and MMInfra logged successful feature ID 13. Receipts:
`logs/v48-mbox-probe-1792960568682816118/`,
`logs/v48-tinysys-probe-1792960608384969305/`, and
`logs/v48-mminfra-probe-1792960634473172367/`.

The corrected display bootstrap reused those verified suppliers, loaded the
remaining modules into RAM, and registered connected 1240×2772 DRM:
`logs/v48-display-bootstrap-1792960667157909902/`. A single three-second
DMA-BUF color-bar modeset returned **exit 0** on the same boot, with Alpine,
SSH, eight services, and ext4 healthy. The MMInfra BUG was fixed, but the
kernel log contains CMDQ error interrupts with `err:-22` and repeated
`cannot get dev ... domain`; the original narrow parser missed them. Its
live kernel log is preserved at `logs/v48-dmabuf-trial-1792960703241053029/`.
Noob watched a later 15-second test and reported the screen stayed black;
that trial is `logs/v48-dmabuf-trial-1792962915844407881/` and shows the
same CMDQ errors. The CRTC is disabled at the end of each test. Display
output is **not working yet**. The GCE devices have `iommus` device-tree
properties, but no visible `iommu_group` links; source review shows the
`cannot get dev ... domain` message follows a null IOMMU domain lookup.
Whether missing early IOMMU binding is the cause still needs verification.
No boot partition changed. On the next boot these modules will need the
corrected bootstrap order; they are not persistent.

## Latest — 2026-10-25 V48 display trial and recovery

On V48 boot `82485906-271a-4949-88f6-3a00acd236cb`, the guarded RAM-only
display bootstrap loaded the matching stock CMDQ platform, tinysys SCMI,
MMInfra debug, and remaining display dependencies. It bound DSI once and
registered connected 1240×2772 `/dev/dri/card0`. The DMA-BUF test allocated
and imported a framebuffer. Receipts are
`logs/v48-display-bootstrap-1792959952071736454/result.json` and
`logs/v48-dmabuf-trial-1792960004528604050/result.json`.

One three-second color-bar attempt caused a kernel BUG at
`mtk-mminfra-debug.c:215` inside `mtk_mminfra_pd_callback`, reached from
`cmdq_mbox_enable` during display modeset disable. The source line is an
explicit `BUG_ON(1)` when the HRE restore register at `0x1e800280` does not
equal `0xfff`. Pstore was captured in the trial receipt. The device rebooted
itself; BusyBox rescue returned first, then Alpine 3.24.2 on boot
`89ee3cfd-fb7c-4c66-94ec-7ae1a12d6f73`. All eight services and ext4
health passed; battery was 52% and 26.7°C. **Do not repeat display modeset**
until the HRE restore failure and its required initialization are understood.
No boot partition changed. Visible pixels remain unproven.

## Latest — 2026-10-25 V48 Alpine boots on 192.168.100.7

Noob requested the newest Alpine candidate. Rescue V19 had stayed online for
94 of 95 twenty-second checks before Noob restarted it into Fastboot. A
read-only thirty-minute MT6375 trend showed nearly flat battery voltage and
zero input-current ADC readings; it did not prove charging. The rescue-only
monitors were stopped. Fastboot identity/layout and the V48 image/rollback
hashes passed again. V48 was flashed to **boot_a only**, leaving the battery
level recorded as unknown at flash time. The flash and separate reboot
receipts are `logs/v48-boot-a-trial-1792948228582606428/result.json` and
`logs/v48-boot-a-trial-1792948264862165835/result.json`.

The new observer covered **both** historical Lynx IPs, `192.168.100.7` and
`192.168.100.8`. On `.7`, pinned port-22 SSH verified the exact V48 init
SHA-256 and stock kernel. Pinned port-2222 SSH then verified Alpine 3.24.2
three times on boot ID `82485906-271a-4949-88f6-3a00acd236cb`; receipt:
`logs/v48-first-boot-1792948259460925317/events.jsonl`. The prior V48
watch only checked `.8`, so its lack of SSH did not establish boot failure.

Current Alpine has OpenRC PID 1 on ext4. All eight default services (health,
battery reserve, local logs, Wi-Fi, Dropbear, maintenance, power history, and
time sync) report status 0. Rootfs has about 534 MiB available; a read-only
kernel-log scan found no ext4 or I/O errors. Early gauge
samples showed 29% capacity, 29.8°C battery, approximately +130 mA signed
gauge current, and CPU temperature falling from 37.8°C to 36.1°C. The
charger supply still reported `online=0`, `Not charging`; actual charging
remains unverified. A read-only ten-sample stability watch completed with
**10/10 healthy samples** on the same boot ID at
`logs/v48-stability-1792948664611119402/`. Capacity rose from 29% to 30%
and battery temperature fell to 28.0°C. The identity-checked V48 poweroff
tool passed a dry run without shutting Lynx down; receipt:
`logs/lynx-poweroff-1792948942961633755/result.json`.

Persistent boot diagnostics were read and checksum-verified in
`logs/v48-bootdiag-capture-1792948601473840898/` (44 records). The current
boot records `HEALTH_READY`, `HANDOFF_BEGIN`, and `TIMER_CANCELLED`.

## Latest — 2026-10-25 one-hour read-only charge trend started

V19 rescue SSH continues online. With Lynx plugged in, MT6375 ADC channel
`in_voltage1` read about 4.92 V at the input. Four closely spaced reads of
`in_current5_raw` (the presumed IBUS channel) were zero; `in_current6_raw`
was zero or one. The power-supply entry still reported `online=0` and
`Not charging`. These readings do not measure actual Nexus USB-port draw and
do not prove net battery charging. The V19 image has no battery-gauge snapshot
driver loaded. Read-only source data was saved in
`logs/rescue-continuity/charger-adc-samples-1792946487803002563.json`.

`tools/observe_lynx_charge_hour.py` is now sampling the same ADC over pinned
SSH every five minutes for one hour. Its status and final trend will be in
`logs/rescue-charge-hour/`; it performs no phone writes. The independent
20-second SSH continuity monitor remains active.

## Latest — 2026-10-25 rescue SSH continuity monitor running

At Noob's request, `tools/monitor_lynx_rescue.py` now checks pinned V19 SSH
on `192.168.100.7` every 20 seconds and records each result, outages, and
boot-ID changes under `logs/rescue-continuity/`. The first two checks
succeeded on boot ID `7dc7336d-00ce-4873-ac7b-2d3b86110cfe`; the monitor
process remains active. Use `python3 tools/monitor_lynx_rescue.py --status`
to inspect it and `--stop` to end it. This checks sampled online continuity,
not whether the battery is charging. The phone is unchanged by this monitor.

## Latest — 2026-10-25 V19 BusyBox rescue boot verified

After the inconclusive V48 and cable-connected V47 boots, Noob requested
rescue mode. Fastboot preflight matched Lynx and the saved V19 BusyBox image
was restored to **boot_a only**. Fastboot reported transfer/write OK; receipt:
`logs/v34-boot-a-trial-1792945597820040814/result.json`. The V19 listener
was armed before the separate reboot. It received Lynx's beacon, verified
pinned native SSH at `192.168.100.7`, and successfully sent the acknowledgment
that cancels V19's fallback reboot. Receipt:
`logs/wifi-v19-contact-1792945637427840925/result.json`. A second direct
pinned SSH command succeeded on boot ID
`7dc7336d-00ce-4873-ac7b-2d3b86110cfe`. Lynx remained plugged in for this
trial at Noob's request. No battery or charging control was tested in this
step. Current first priority is preserving this rescue foothold.

## Latest — 2026-10-25 V48 first hardware trial inconclusive

Noob charged Lynx, confirmed she was cool, and connected Fastboot on Nexus.
Read-only preflight matched serial `89BYAY5L4T9HFUOV`, product, unlocked
slot A, bootloader version, and partition sizes. The independently validated
V48 image was flashed to **boot_a only**; Fastboot reported transfer and write
OK. The guarded trial tool left her in Fastboot until the receipt was checked,
then a separate Fastboot reboot was requested. Receipts:
`logs/v48-boot-a-trial-1792943765836858381/result.json` and
`logs/v48-boot-a-trial-1792943824394357269/result.json`.

A read-only observer ran for 10 minutes. Neither pinned SSH port 22 nor 2222
opened; after the reboot Nexus no longer saw a Lynx USB device or Fastboot
endpoint. `logs/v48-first-boot-1792943820471549585/events.jsonl` contains
the observation. No second flash or reboot occurred. No boot success or
charging-control result can be claimed. Noob reports that Lynx feels cool;
screen state is pending. The V47 rollback image remains verified locally.

## Latest — 2026-10-24 V48 charger boot fix prepared offline

Noob reported that Lynx is away from Nexus and charging; current battery
capacity is unknown. Nexus cannot reach her pinned SSH ports at
`192.168.100.8`. No phone write or reboot occurred in this preparation.
The exact V47 `/init` has two charger-triggered poweroff blocks. Its health
startup supplement has a third charger-online refusal that would otherwise
fail the boot. V48 removes these three refusals while retaining the battery
and thermal health startup. Independent offline validation passed for the
64 MiB boot image. The V47 rollback image and guarded boot_a-only Fastboot
procedure are ready. V48 has not been booted or flashed; charging behavior
and thermal response still require live verification. An optional 98% charge
controller and disabled OpenRC service have been prepared offline, pending a
live MT6375 control test; neither is installed on Lynx. See
`V48-CHARGER-BOOT-FIX.md`.

## Latest — 2026-10-24 powered on, no Wi-Fi or USB contact

Noob put Lynx back on a cable and powered her on with the buttons. She showed
a black screen and felt mildly warm. A seven-minute pinned SSH watcher found
neither rescue port 22 nor Alpine port 2222; a six-minute UDP beacon listener
received no datagram. Nexus saw no Lynx USB device or Fastboot endpoint.
Receipts: `logs/v47-reconnect-1792854380193440511/result.json` and
`logs/wifi-v19-contact-1792854612031922583/result.json`. No phone write,
reboot, or display trial was issued. Next read-only step needs Lynx in
Fastboot on Nexus USB so boot state can be inspected.

Source review of the exact V47 `/init` then found a charger guard after
the Wi-Fi stage: when any power-supply `online` value differs from zero,
it requests poweroff, and a five-second watcher repeats that policy. This
can explain a cable-powered shutdown after Wi-Fi setup. V47's local Wi-Fi
path does not send the old UDP beacon, so absence of that beacon was not
evidence of Wi-Fi failure.
Noob was asked to unplug the cable and start Lynx with the buttons while a
new pinned listener was active. A fresh SSH result is pending. The offline
display/touch trial guards now require charger `online=0` and at least 50%
battery; they will not run at the last measured 38%.

## Latest — 2026-10-24 shutdown requested after battery fell to 38%

The last healthy V47 Alpine check had 38% battery, a cool 24.6°C pack,
all eight services healthy, and zero ext4 errors. The MT6375 charger
reported `online=0`, `Not charging`; the gauge-current sign alone is not a
charging proof. An identity-checked OpenRC poweroff request was sent and SSH
disappeared (`logs/lynx-poweroff-1792853724641835014/`). Noob reported that
the cable woke Lynx again and removed it. A seven-minute bounded watcher saw
no Alpine return, and a final SSH check found no route to ports 22 or 2222.
Receipts: `logs/auto-poweroff-1792853784524531996.json` and its final check.
This supports Lynx staying off; physical power state still needs a screen
check. Live display/touch work waits for a verified charging state.

## Latest — 2026-10-24 live V47 Alpine, display and touch trials

Lynx is on boot ID `897cad51-2ae4-479a-98bc-9ab8a052b9a9` with V47 Alpine,
Wi-Fi/SSH, all eight services healthy, and zero ext4 errors. At the last
check the battery was 49%, pack 27.9°C, hottest sensor 35.1°C; charging
was inferred from the signed gauge value but not verified by the charger.
Stock display and touch modules were loaded into RAM only; no boot image or
persistent startup changed. `/dev/dri/card0` and `/dev/input/event0` exist.

The DMA-BUF framebuffer and a three-second CRTC call succeeded in userspace,
but the kernel reported a display CMDQ timeout. Visible pixels are not yet
verified; do not repeat the modeset until that fault is understood. Synaptics
S3910 application firmware was detected, and an input device and IRQ were
registered; real touch coordinates have not yet been captured. The earlier
DMA-BUF modeset without `mtk-mml-mt6983.ko` crashed in MML topology setup,
then V47 recovered automatically. Full evidence and safe repeat tools are in
`V47-DISPLAY-TOUCH-TRIAL.md`.

## Current status — 2026-10-24 powered off after V47 display research

Lynx ran V47 Alpine on boot ID `00841cdb-6658-44d6-9f47-4770b047cad5`
for over 12 hours. At the last healthy check she had 26% battery, a 26.1°C
pack, all eight services running, both SSH paths, and zero ext4 errors.
An identity-checked `openrc-shutdown -p now` was requested through
`tools/lynx_poweroff.py`; SSH disappeared and ping failed. The receipt is
`logs/lynx-poweroff-1792834943387190230/result.json`. Network loss supports
shutdown but cannot independently prove hardware power state; check the
phone itself. Reuse `python3 /noobia/lynx/tools/lynx_poweroff.py --check`
before an orderly poweroff next time.

The display investigation got the matching stock panel bound and created
`/dev/dri/card0` with a connected 1240×2772 DSI connector. This required
six additional stock modules loaded in RAM. A simple DRM pattern still
failed at dumb-buffer allocation, and touchscreen is untested. None of the
display module loads were made persistent. See `V47-DISPLAY-TOUCH-TRIAL.md`.
The charged-boot sequencer and DMA-BUF alternative are prepared offline in
`V47-DISPLAY-OFFLINE-NEXT.md`; neither has been tried on Lynx.

## Current status — 2026-10-23 V47 controlled boot

V47 now also has signed Alpine `curl`, `jq`, `tmux`, and `rsync` installed
on the persistent root after a guarded live health check. A compiler in the
active root remains held because the current repository's `musl-dev-r3` conflicts with
Lynx's pinned `musl-r2`; no libc upgrade was attempted. See
`V47-ALPINE-UTILITIES.md` for the exact receipt and tools.

An isolated native build root under `/var/lib/lynx-devroot` now resolves
the compiler need without changing the active libc. GCC compiled and ran
a small aarch64 C program there, while the active services and exact libc
pins stayed intact. See `V47-ISOLATED-NATIVE-TOOLCHAIN.md`.

The persistent Alpine root now has a read-only `lynx-status` command for
a compact local health and access JSON snapshot. Its first `--assert-ready`
run passed with eight services, Wi-Fi, battery, cooling states, storage,
boot identity, and power-log presence. Schema 2 additionally reports zero
recorded ext4 errors on `/dev/sdc85`. See `V47-LOCAL-STATUS.md`.

Lynx is now on boot ID `9054078d-aafa-4abf-9600-5c70f8234360`, with V47
on `boot_a` and Alpine 3.24.2/OpenRC running on persistent ext4. The V47
boot script hash, checksummed `TIMER_CANCELLED` stage, all eight local
services, NTP sync, prior-boot logs, and Alpine SSH on port 2222 were
verified. A pinned observer showed Alpine through uptime 465 seconds.
The new DHCP retry took its first attempt on this boot, so its actual
retry path remains untested. V46 remains the exact local Fastboot
restoration image. See `V47-DHCP-RETRY-OFFLINE.md` for receipts.

On the same live boot, maintenance events were raised to persistent syslog
severity with the previous script saved under `/root/lynx-rescue/`.
The harmless event proof passed while health, reserve, and maintenance
services stayed active. See `V47-MAINTENANCE-EVENT-LOGS.md`.

The power CSV has one 72-byte zero gap at the V46→V47 transition, while
ext4 reports no current errors. Raw bytes were preserved and a reader now
reports that anomaly explicitly. New samples are flushed to storage after
append, with the old sampler saved for rollback. See
`V47-POWER-HISTORY-GAP.md`.

The maintenance watcher now saves a bounded, read-only carrier/IPv4/nl80211
snapshot when Wi-Fi first degrades. The live healthy snapshot passed, and
the old script is saved for rollback. No outage or radio reset was induced;
see `V47-WIFI-OUTAGE-SNAPSHOT.md`.

## Previous status — 2026-10-23 V46

Lynx is currently on boot ID `f6230cac-8d41-48da-bf28-2700e9ff56f1`,
with the exact V46 `boot_a` image, Alpine 3.24.2/OpenRC PID 1, persistent
ext4 root, Wi-Fi, rescue SSH on port 22, and Alpine SSH on port 2222.
The phone was connected to Nexus for charging; the gauge showed rising
capacity, positive current, and a cool pack. The early charger supply flag
still reads zero, so charging protection behavior is not fully established.

That boot had a tested severity-filtered local logger, verified service
maintenance, signed Alpine diagnostics (`strace`, `lsof`, `iw`), and a local
Chrony service synchronized over Wi-Fi. No boot partition was changed while
these userland additions were made. The persistent reserve script was
rolled back to the original 20% policy for the next boot; the current
process still runs the revised charging-aware guard that started before the
file rollback. See `V46-SELF-MAINTENANCE.md` and
`V46-CHARGING-RESERVE-STAGE.md` for exact receipts and limitations.

At that point V47 was an offline candidate for the specific DHCP failure
seen in two checksummed boot records. Its image and V33 recovery hashes,
changed member scope, AVB model, and retry fixtures had passed before the
controlled hardware trial described above.

## Current status — V46 survived supervised OpenRC reboot

From verified V46 Alpine/OpenRC on port 2222, a guarded OpenRC reboot was
requested with USB unplugged:
`logs/v46-openrc-reboot-1792698093555567903/result.json`. Pinned Wi-Fi SSH
returned on **new** boot ID `135b8a44-fc09-427c-9b5f-53ac4add7527`.
Exact V46 `/init`, automatic Alpine 3.24.2/OpenRC PID 1, health service,
checksummed `TIMER_CANCELLED` record, and Alpine-owned SSH on port 2222 all
passed:
`logs/v46-autonomous-alpine-verification-1792698342972918504/result.json`,
`logs/v46-same-boot-stage-1792698347517032429/result.json`, and
`logs/v46-alpine-native-ssh-1792698347516583825/result.json`.
**V46 remains installed and Alpine is running on the second boot.** The
bounded observer recorded 155 complete same-boot SSH samples through Alpine
uptime 453.95, past the old timer. Cross-receipt and sample-hash verification:
`logs/v46-reboot-verification-1792698593054541557.json`.
This proves a supervised warm reboot; a full power-off cold start and
every-start reliability remain unproved.

## Current status — V46 autonomous Alpine running beyond startup deadline

The second guarded V46 trial wrote **only `boot_a`**, then rebooted with USB
unplugged. Pinned Wi-Fi SSH verified exact V46 `/init` on boot ID
`917238d2-f2c3-479b-9ded-6f677c474763`. Its checksum-verified persistent
record has `HEALTH_READY` at uptime 211 and `HANDOFF_BEGIN` plus
`TIMER_CANCELLED` at 221:
`logs/v46-same-boot-stage-1792697419990383186/result.json`. Independent
verification passed for autonomous Alpine 3.24.2/OpenRC PID 1, persistent
ext4 root, health service, Wi-Fi SSH, Python, and Git:
`logs/v46-autonomous-alpine-verification-1792697396638346147/result.json`.
Alpine-owned pinned SSH on port 2222 passed independently:
`logs/v46-alpine-native-ssh-1792697679963651084/result.json` (BusyBox rescue
SSH stays on port 22).
The bounded observer finished with 233 complete same-boot SSH snapshots,
one timeout followed by recovery, and Alpine PID 1 through uptime 672.51,
beyond V45's uptime-428 startup-timer boundary:
`logs/v46-health-window-1792697094431894340/result.json`.
**V46 is installed and Alpine is running.**
Cold boot reliability, the intermittent early UFS probe, and sustained
charging remain unproved. Exact V33/V19 `boot_a` rollback images are intact.
See `docs/V46-PERSISTENT-ALPINE.md`.

## Earlier status — first V46 trial stopped early; V33 recovered

The first guarded V46 trial wrote **only `boot_a`** and rebooted unplugged.
Its pinned observer saw no V46 SSH contact during the first five minutes.
After Fastboot returned, read-only PL/LK was captured and exact V33 restored
**only to `boot_a`**. Pinned Wi-Fi SSH, V31 RAM health, guarded handoff, and
Alpine/OpenRC PID 1 passed:
`logs/v33-alpine-pid1-verification-1792682811956277416/result.json`.
The recovered checksum-verified persistent trace contains no new V46 boot
record: `logs/v38-persistent-capture-1792682815070129601/result.json`.
The pinned V33 contact's pstore snapshot holds an **older** UFS trace with
token `69adf9d14707d848063b861b8f248748`, which differs from exact V46's
`c4086e17473b3a2b59f233cfb0d98438`:
`logs/pstore-retained-token-1792697932761260892.json`. The earlier
`logs/pstore-previous-boot-1792683031840922664.json` misattributed it to
V46 and is superseded. The first V46 stop point remains unknown.
**V33 is installed and Alpine is running.** See `docs/V46-PERSISTENT-ALPINE.md`.

## Current status — V45 recovered; V33 Alpine running

After the successful bounded V45 autonomous handoff, read-only PL/LK was
captured and exact V33 restored **only to `boot_a`**:
`logs/pllk-1792680361644628571.json` and
`logs/v34-boot-a-trial-1792680364357344162/result.json`. Unplugged boot,
pinned Wi-Fi SSH, V31 RAM health, guarded handoff, and Alpine/OpenRC PID 1
passed: `logs/v33-alpine-pid1-verification-1792680518669188817/result.json`.
The recovered checksummed V45 record confirms stages through `HANDOFF_BEGIN`:
`logs/v38-persistent-capture-1792680522879753845/result.json`.
**V33 is installed and Alpine is running.** V46 remains offline and unflashed.

## Offline next candidate — V46 persistent Alpine startup

V46 derives from the autonomous V45 handoff and cancels the outer startup
timer only after three passing health checks, a checksummed handoff marker,
and successful local helper load. It keeps the independent health watchers,
charger guard, and parent power-off fallback. The builder, independent
validator, guarded `boot_a` trial preparation, and parser fixture passed.
This paragraph records V46 preparation before its first hardware trial.
Exact V33 had been restored and Alpine
verified. The V46 pinned observer correctly rejected live V33 as V46 while
seeing Alpine PID 1: `logs/v46-health-window-1792680522964230929/result.json`.
See `docs/V46-PERSISTENT-ALPINE.md`.

## V45 autonomous Alpine handoff passed and recovered

V45 was flashed only to `boot_a` after offline validation and fresh Fastboot
preflight. Pinned SSH verified exact V45 `/init` and the same boot ID reached
Wi-Fi ready at uptime 96, health ready at 208, and local handoff start at 218.
Independent proof verified Alpine 3.24.2/OpenRC as PID 1, health service,
persistent root, Wi-Fi SSH, and no host arming marker:
`logs/v45-autonomous-alpine-verification-1792678596444971030/result.json`.
The collector retained Alpine SSH through uptime 428.30, then lost contact
at the expected bounded timer boundary. Exact V33 restoration and Alpine
verification are recorded above. See `docs/V45-WIFI-FAILURE-CODE.md`.

## Offline next candidate — V45 Wi-Fi failure code and local OpenRC probe

V45 is built and independently validated offline. It keeps V44's bounded
local OpenRC handoff but, if Wi-Fi fails first, records the Wi-Fi worker's
numeric result or the absence of a result in the checksummed persistent
stage log. The guarded trial `--prepare`, parser fixture, and read-only
pinned collector dry run passed. This paragraph records the preparation
state before the hardware trial above. See `docs/V45-WIFI-FAILURE-CODE.md`.

## Current status — V44 Wi-Fi failed before handoff; V33 Alpine restored

The first guarded V44 trial wrote **only `boot_a`** and rebooted separately.
Its pinned SSH collector saw no contact. After Fastboot returned, exact V33
was restored only to `boot_a`; pinned SSH, V31 health, and Alpine/OpenRC PID 1
passed: `logs/v33-alpine-pid1-verification-1792677239930378372/result.json`.
The recovered checksummed V44 boot record has `START` at uptime 8 and
`WIFI_FAILED` at 98, with no health or OpenRC stage:
`logs/v38-persistent-capture-1792677243171127255/result.json`. V44's new
handoff branch has therefore **not** been hardware-tested. A single Wi-Fi
failure could be transient; its exact worker reason was held only in RAM.
See `docs/V44-LOCAL-OPENRC-PROBE.md`.

## Offline next candidate — V44 bounded local OpenRC probe

V44 is built and independently validated offline. It derives from proven
V43, keeps its complete supplement and stock kernel, and changes only
primary `/init`: after three passing health checks, call the already
packaged local authority OpenRC helper. It retains the 420-second outer
power-off timer, so even a successful handoff remains a bounded trial.
The guarded `boot_a` trial `--prepare` and a pinned collector dry run passed.
This paragraph records the preparation state before the first hardware
trial above. See `docs/V44-LOCAL-OPENRC-PROBE.md`.

## Current status — V43 bounded health passed; V33 Alpine restored

V43 was flashed only to `boot_a` after offline validation and fresh Fastboot
preflight. Pinned Wi-Fi SSH verified exact V43 `/init` and the health child
reached `HEALTH_READY` at uptime 208.10. Lynx remained reachable through
uptime 303.11 with passing parent postchecks, then the next sample timed out.
The checksum-verified persistent record confirms `END` at uptime 304:
`logs/v38-persistent-capture-1792674289456124190/result.json`.
Exact V33 was restored **only to `boot_a`** after read-only PL/LK capture.
Pinned SSH, V31 RAM health, guarded handoff, and Alpine/OpenRC PID 1 passed:
`logs/v33-alpine-pid1-verification-1792674286205723296/result.json`.
**V33 is installed and Alpine is running.** Autonomous handoff is the next
unproved step. See `docs/V43-HEALTH-TOLERANCE.md`.

## Earlier preparation — V43 three-sample health tolerance

V43 changes only primary `/init` from exact V42. In the post-readiness
observation window it counts consecutive supervisor `--once` failures and
requests power-off only on the third, matching the independent supervisor's
existing safety threshold. Success resets the count. All watchers, charger
guard, 420-second outer timer, final power-off at uptime 300, stock kernel,
and supplement remain unchanged. The builder, independent validator, guarded
trial preparation, and pinned collector dry run passed. This paragraph
records the preparation state before the successful hardware trial above. See
`docs/V43-HEALTH-TOLERANCE.md`.

## Current status — V42 post-readiness refusal proven; V33 recovered

V42 was flashed **only to `boot_a`** after offline validation and fresh
Fastboot preflight. Pinned Wi-Fi SSH verified exact V42 `/init` through uptime
210.33; the next sample lost contact. After Fastboot returned, exact V33 was
restored only to `boot_a`. Its first reboot lacked SSH, but the second reached
pinned SSH; V31 RAM health and Alpine/OpenRC PID 1 passed:
`logs/v33-alpine-pid1-verification-1792667635515102275/result.json`.
**V33 is installed and Alpine is running.**

The checksum-verified persistent capture
`logs/v38-persistent-capture-1792667638510281486/result.json` contains three
V42 boot IDs. All reached `HEALTH_READY` at uptime 209–211 then recorded
`HEALTH_FAIL_POSTCHECK` within one second. The immediate post-readiness
supervisor `--once` check requests power-off. Its inner failed condition is
unknown. Investigate or tolerate isolated samples while retaining the
independent supervisor's three-consecutive-failure safety policy. See
`docs/V42-POST-READY-TRACE.md`.

## Current status — V41 health ready, contact lost later; V33 recovered

V41's parent-only retry image was flashed **only to `boot_a`** after offline
validation and fresh Fastboot preflight. Pinned Wi-Fi SSH verified exact V41
`/init` through uptime 207.94; the next sample lost contact. After Fastboot
returned, a read-only PL/LK log was saved and exact V33 was restored only to
`boot_a`. Pinned rescue SSH, V31 RAM health, and Alpine/OpenRC PID 1 all
passed: `logs/v33-alpine-pid1-verification-1792659494972296336/result.json`.
**V33 is installed and Alpine is running.**

The checksummed persistent capture
`logs/v38-persistent-capture-1792659498990866325/result.json` found four V41
boot IDs. All reached `HEALTH_READY` at uptime 196–208; none recorded the
planned `END` at 300. This proves parent health startup succeeded, while the
post-readiness loss remains unclassified. The current V41 loop can request
power-off on a single failed supervisor sample without saving a stage reason.
Instrument that path before another flash. See `docs/V41-PRIMARY-RETRY.md`.

## Current status — V40 gave no stage record; V33 Alpine recovered

V40 was trialled on `boot_a` after offline checks and a fresh Fastboot
preflight. Its pinned Wi-Fi collector saw no candidate during the unplugged
boot window. After Fastboot returned, exact V33 was restored only to
`boot_a`. The first V33 boot did not reach SSH; a second Fastboot reboot did.
Its pinned rescue SSH and V31 RAM health passed, then OpenRC/Alpine PID 1 was
verified at `192.168.100.4`:
`logs/v33-alpine-pid1-verification-1792617781090767073/result.json`.
**V33 is installed and Alpine is running.**

The read-only persistent-log capture
`logs/v38-persistent-capture-1792617783351689411/result.json` found only
the previously verified V38 and V39 files, with no V40 record. V40 may have
stopped before its first `START` write or that write may have failed; the
cause remains unproven. The two PL/LK snapshots and USB disconnect/reconnect
events are preserved. Review V40's modified supplementary payload and early
stage recording before another flash. See `docs/V40-HEALTH-PARENT-RETRY.md`.

## Current status — V39 health refusal; V33 Alpine restored

V39's persistent log was recovered and verified after returning to V33. It
records `HEALTH_BEGIN` at uptime 190 and **`HEALTH_FAILED` at 195**, with no
`HEALTH_READY`. The V31 child had already reported ready and left a zero
result, so the failure occurred after child startup but before the parent's
success return; its exact failed check is not yet known. The loss of SSH at
that time matches V39's deliberate power-off on health failure. Full record
and checksums: `logs/v38-persistent-capture-1792616489493406914/result.json`.

Before restoration, the read-only preloader/LK log was captured at
`logs/pllk-1792616343259834392.json`. Its UFS and reset entries have not
been tied to this V39 failure. Fresh Fastboot identity/layout preflight passed,
and exact V33 was restored **only to `boot_a`** without implicit reboot:
`logs/v34-boot-a-trial-1792616345589715157/result.json`. A separate reboot,
pinned rescue SSH, V31 RAM health, V33 handoff, and independent Alpine/OpenRC
PID 1 verification passed:
`logs/v33-alpine-pid1-verification-1792616485891521272/result.json`.
**V33 is installed; Alpine is last verified running unplugged.** Investigate
the parent health check before another flash.

## Prior status — V39 contact lost; V33 restoration pending

V39 was flashed **only to `boot_a`** after a fresh Fastboot preflight and
rebooted with the pinned collector already running. No other partition was
written. Exact V39 `/init` and SSH were verified on boot ID
`30131789-21c8-4367-8c45-4fadc37ef7dc` from uptime 93.49 to 195.48.
`HEALTH_BEGIN` was logged at 190.84. The packaged V31 health child loaded
its modules, reported `READY_ON_PHONE_MONITORING_ACTIVE`, and wrote a zero
child result by 195.48, but the parent `HEALTH_READY` marker was not yet
captured. The next SSH sample failed, and there has been no pinned contact
since. The independent V39 safety deadline elapsed. **At that point V39 was
still the last image written to `boot_a`; Alpine was not yet recovered.**
Raw evidence and incident summary are in
`logs/v39-health-window-1792615806259628878/`. Exact V33 rollback has
already been verified offline. Noob has been instructed to enter Fastboot and
connect USB. Once Fastboot is confirmed, first attempt the read-only
preloader/LK log, then use the guarded V33-only `boot_a` restoration. Stop on
any unexpected identity or partition layout. After restoring V33, separately
reboot unplugged, verify pinned rescue SSH, run V31 RAM health and V33 handoff,
verify Alpine/OpenRC PID 1, and retrieve V39's persistent stage log. The
cause of contact loss remains unknown.

## Prior offline candidate — V39 delayed health

V39 retains V38's verified Wi-Fi/SSH and persistent stage recording, waits
until uptime 190 seconds, then invokes the already packaged V31 health path
once while keeping BusyBox as PID 1. It omits Alpine handoff and has bounded
power-off and charger guards. Its exact V38-parent image, unchanged stock
kernel/supplement, health script bytes, and V33/V19 rollback images passed
offline validation. The guarded trial tool and collector dry run passed.
This was its offline preparation state before the trial above. See
`docs/V39-DELAYED-HEALTH.md`.

## Current status — V38 completed; V33 Alpine restored

V38 booted BusyBox with the exact expected `/init` hash and remained
reachable over pinned Wi-Fi SSH from uptime 93.05 through 189.51 seconds.
Its checksummed persistent log has verified markers at start, Wi-Fi ready,
120/150/180 seconds, and the deliberate 190-second end. The collector's
snapshot at uptime 190.89 timed out at the planned shutdown boundary.
Details and receipts: `docs/V38-PERSISTENT-TRACE.md` and
`logs/v38-persistent-capture-1792615448786856168/result.json`.

After a fresh Fastboot preflight, exact V33 was restored **only to `boot_a`**
(`logs/v34-boot-a-trial-1792615245603834462/result.json`). A separate reboot,
pinned SSH, V31 RAM health, guarded V33 handoff, and Alpine/OpenRC PID 1
verification passed on boot ID `948712a7-ea62-4c7e-9f91-e46b33547a2d`
(`logs/v33-alpine-pid1-verification-1792615414672211297/result.json`).
Lynx is unplugged, with Alpine last verified running. Autonomous cold boot
remains unproved; V38 intentionally excluded health and Alpine handoff.

## Prior status — V38 trace prepared offline; V33 Alpine running

V38 is an **unflashed, unbooted** short diagnostic designed to record which
boot stages execute when pinned SSH never appears. It would make a few
checksummed writes to the existing verified Alpine ext4 root, then unmount
after each record. Its image and exact V33/V19 rollback inputs passed offline
validation, and the collector/parser/retrieval tools passed local checks.
The remaining ext4 mount/write and hardware behavior risks are explicit in
`docs/V38-PERSISTENT-TRACE.md`. No flash, reboot, or explicit phone storage
write was performed in preparing V38.
V33 remains installed on `boot_a`; Alpine/OpenRC and direct Wi-Fi SSH were
last verified on boot ID `dd9abd57-33f0-46e0-8376-e714d46eef26`.

## Current status — V37 no-contact attempt ended; V33 Alpine restored

The guarded V37 Wi-Fi-only diagnostic wrote only `boot_a` and separately
rebooted after a fresh Fastboot preflight. The prestarted pinned collector
saw zero SSH samples over about 287 seconds. Lynx then reappeared in Fastboot
on USB; the collector was stopped. A fresh identity/layout preflight passed
and exact V33 was restored only to `boot_a`, with no implicit reboot:
`logs/v34-boot-a-trial-1792601253452132247/result.json`. A separate reboot
with a prestarted pinned collector, physical USB removal, V31 RAM health
startup, and guarded V33 handoff followed. **Alpine 3.24.2/OpenRC PID 1,
direct port-2222 SSH, and charger offline are verified** on fresh boot ID
`dd9abd57-33f0-46e0-8376-e714d46eef26`:
`logs/v33-alpine-pid1-verification-1792601501041777035/result.json`.
Read-only post-trial pstore still contains only the older UFS token, and the
first 0xf0000 bytes of expdb have the exact same SHA-256 as five earlier
captures. Neither gives a V37 reset cause. The V37 run does not prove whether
the diagnostic executed Linux userspace or reached Wi-Fi. See
`docs/V37-WIFI-WINDOW-DIAGNOSTIC.md` and
`logs/v37-wifi-window-1792600960480583281/incident-summary.json`.

## Prior offline follow-up — V37 diagnostic preparation

The V37 Wi-Fi-only, bounded diagnostic is built and independently validated
offline. It changes only the primary init tail from V36, observes pinned SSH
until uptime 190 seconds without starting health, and then requests power-off.
It is not a daily boot image. The exact image hash, collector dry run, guarded
trial and V33 restoration procedure are in `docs/V37-WIFI-WINDOW-DIAGNOSTIC.md`.
**This paragraph records V37's preparation state before its later trial.**
V33 is again installed and Alpine/OpenRC is the last verified running PID 1.
A 30-second dense read-only collector on the
healthy V33 boot completed 31/31 SSH samples without timeout:
`logs/v34-health-window-1792600459590278195/result.json`.

## Current status — V33 restored; Alpine/OpenRC and SSH verified

On 2026-10-21 the bounded Fastboot watcher matched Lynx's exact serial and
completed a fresh identity/layout preflight. It restored the exact working V33
image (SHA-256 `1d65456979d8a48d31de77c987b8aaf9b5ac11af62c51d00fdaff68ad47e747f`)
**only to `boot_a`**, without an implicit reboot. Receipts:
`logs/v36-fastboot-restore-watch-1792598851382787076/result.json` and
`logs/v34-boot-a-trial-1792599609524961827/result.json`.

A separate Fastboot reboot followed with the pinned collector already running;
Noob unplugged USB. V33 rescue SSH was verified at `192.168.100.7` and its
fallback cancelled (`logs/dynamic-pinned-contact-1792599872928843421/result.json`).
The unplugged V31 RAM health startup passed
(`logs/local-health-v31-ram-trial-1792599991891862635/result.json`), the
same-boot V33 handoff was armed
(`logs/v33-openrc-arm-1792600013304397949/result.json`), and independent
verification proved **Alpine 3.24.2/OpenRC PID 1, Wi-Fi/SSH, persistent ext4
root, and health service** on boot ID
`0e5eaa29-d233-4e12-a7b7-508926575156`:
`logs/v33-alpine-pid1-verification-1792600019836843440/result.json`.
Alpine's own `lynx-wifi` and `lynx-dropbear` OpenRC services were reported
started, and a separate pinned-key login directly into Alpine on port 2222
proved the same boot ID and `/sbin/openrc-init`:
`logs/alpine-direct-ssh-2222-1792600242750752502/result.json`.
No partition was written in the reboot, health, or Alpine handoff sequence.
V33 is installed; Alpine was last verified running. Its startup still needs a
host-assisted health/handoff step on every fresh boot. Do not claim autonomous
cold boot from the failed V34–V36 trials.

## Prior status — V36 trial booted twice; V33 rollback was pending

On 2026-10-21, Noob connected Lynx in Fastboot. Fresh identity/slot/layout
preflight matched at `logs/fastboot-preflight-1792598261484010058.json`.
With the pinned collector already listening, exact V36 was flashed **only to
`boot_a`** (`logs/v36-boot-a-trial-1792598264817606971/result.json`) and
rebooted separately (`logs/v36-boot-a-trial-1792598272107504358/result.json`).
Noob was instructed to unplug USB immediately. The collector verified the
exact V36 `/init` hash at `192.168.100.7` on two autonomous boots:
`logs/v36-cooldown-window-1792598257537328145/`.

Boot `629b4b71-d9ca-4698-862b-79adb854d35a` reached the 40-second cooldown,
local V31 health child result 0, and `health-bootstrap/ready`, then lost SSH
after a final successful sample at uptime 150.72 seconds. Boot
`7ae95874-58c3-4cc7-9d3e-d5c962603da3` reached the cooldown and cooling
watcher, with one passing health sample, then lost SSH after uptime 165.07
seconds before a child-ready marker. The high-frequency collector was stopped
after two lost contacts; timeline and partial samples are preserved. A read-only
pstore capture on the second boot still contained the **older** UFS token, not
a V36-specific crash. See the raw incident summary at
`logs/v36-cooldown-window-1792598257537328145/incident-summary.json`.
The 40-second wait did not make local health startup reliable. The precise
reset/contact-loss mechanism remains unknown; do not call this a thermal
shutdown or kernel crash without matching evidence.

**V36 remains the last image written to `boot_a`; V33 rollback is pending.**
Noob has been asked to enter Fastboot and plug USB. A bounded host watcher is
already listening at
`logs/v36-fastboot-restore-watch-1792598851382787076/result.json`; it accepts
only Lynx's exact serial, then invokes the existing guarded V33-only `boot_a`
restoration with a fresh Fastboot preflight, and does not reboot. Stop if
Fastboot identity or partition layout differs. Do not start another Linux
trial until V33 recovery has been verified.

## Current status — V33 Alpine running; V36 cooldown trial prepared offline

On 2026-10-21, Noob connected Lynx in Fastboot. Fresh read-only preflight
matched serial, unlocked slot A, bootloader and partition layout at
`logs/fastboot-preflight-1792597128509436454.json`. The already installed V33
was rebooted **without flashing**. A prestarted pinned dynamic collector found
Lynx at `192.168.100.7`, cancelled the V33 fallback and saved raw pstore/boot
logs: `logs/dynamic-pinned-contact-1792597143051616612/result.json`.
The phone reported its charger offline. V31 RAM health startup passed at
`logs/local-health-v31-ram-trial-1792597302279562296/result.json`; the V33
handoff was armed at `logs/v33-openrc-arm-1792597321334700437/result.json`;
independent Alpine/OpenRC PID 1 verification passed at
`logs/v33-alpine-pid1-verification-1792597329528303612/result.json`.
**V33 remains installed, with Alpine last verified running.** No partition
write occurred in this return-to-Linux sequence.

V36 is an **offline-only** timing diagnostic prepared from exact V35. It adds a
40-second cooldown after local Wi-Fi/SSH readiness before the same V31 health
startup, then keeps monitored BusyBox for a bounded observation window. Image
SHA-256 is `75bbd8b44d728a1264f55ce3aff521400d25ea6b3e900c8bacca757cdfe49a50`.
Builder, independent validation, collector dry run, guarded trial tool and
rollback details are recorded in `docs/V36-COOLDOWN-TRIAL.md`. V36 has **not**
been flashed or booted on Lynx. Its timing hypothesis is unproved.

## Offline follow-up while Noob is away — 2026-10-21

The V34/V35 failure boundary has been rechecked against raw captures in
`docs/V34-V35-FAILURE-BOUNDARY.md`. V34 reached local health startup twice but
lost pinned SSH near cooling-watcher startup without a captured health-ready
or Alpine result. V35 captured no pinned SSH at all. The retained pstore is
older and gives no cause for these trials. The read-only V34/V35 collector now
captures PID 1 identity/status, process and kernel tails, health timer/events,
and hashes raw samples. A live **read-only** smoke capture on the restored V33
Alpine boot passed at
`logs/collector-v33-readonly-smoke-1792586062632995585/result.json`.
V33 remains installed; no flash or reboot was done in this follow-up.

## Current status — V35 no-contact trial ended; V33 Alpine restored

On 2026-10-21, fresh Fastboot preflight matched Lynx's recorded serial and
layout (`logs/fastboot-preflight-1792585206698886761.json`). The guarded V35
trial wrote **only `boot_a`**, then issued a separate reboot:
`logs/v35-boot-a-trial-1792585214468026235/result.json` and
`logs/v35-boot-a-trial-1792585220570512516/result.json`. USB disappeared.
The pinned dynamic collector ran before reboot and saw **zero SSH samples**;
Noob then reported Lynx in Fastboot. The collector was stopped at about 280
seconds because the phone had returned to Fastboot. Preserve the raw receipt
and human-observation summary at
`logs/v35-health-window-1792585210711416723/`. This trial did not prove
that V35 executed Linux userspace or reach the intended health-only split;
its return-to-Fastboot cause is unknown. Do not interpret it as a health or
Alpine handoff verdict.

Noob connected Fastboot on USB. A fresh preflight matched identity, slot and
layout (`logs/fastboot-preflight-1792585497614933929.json`). Exact V33 was
restored **only to `boot_a`**:
`logs/v34-boot-a-trial-1792585500575066240/result.json`. A separate reboot,
USB removal, dynamic pinned SSH, and pstore capture followed:
`logs/dynamic-pinned-contact-1792585509213161234/result.json`. Pstore still
contained the older UFS trace, not a new V35-specific crash. The same boot
passed V31 RAM health
(`logs/local-health-v31-ram-trial-1792585631681747370/result.json`), guarded
V33 arm (`logs/v33-openrc-arm-1792585654274516251/result.json`) and the
independent Alpine PID 1 verifier
(`logs/v33-alpine-pid1-verification-1792585658074948913/result.json`).
**V33 is the current installed `boot_a`, and Alpine/OpenRC is the last
verified PID 1.** V35 remains an unproved offline diagnostic artifact.

The V34 local-authority OpenRC guard was also probed read-only on this healthy
V33 boot. The first probe had an incorrect precondition: it expected the RAM
`local-boot-ready` marker to be absent, but V33's host-assisted health launcher
had already set it. It refused before invoking the guard; that receipt is
`logs/local-openrc-guard-probe-1792585735073047773/result.json`. The corrected
probe used the existing matching token and passed the local-authority guard
at 29.6°C battery and 38.2°C maximum thermal sensor:
`logs/local-openrc-guard-probe-1792585760395182111/result.json`. This proves
the local guard can pass in a healthy V33 state; it does not prove V34 reached
the guard or explain the V35 no-contact boot.

## Current status — V33 restored again after the V34 diagnostic retrial

Noob returned Lynx to Fastboot. Fresh preflight matched the same serial,
unlocked slot A, bootloader, and partition layout:
`logs/fastboot-preflight-1792584299193355594.json`. Exact V33 was written
**only to `boot_a`**, with no implicit reboot:
`logs/v34-boot-a-trial-1792584306023674565/result.json`. A separate Fastboot
reboot succeeded and USB disappeared. Pinned SSH at `.6` proved V33 BusyBox
and saved pstore before health startup:
`logs/dynamic-pinned-contact-1792584314050097198/result.json`. Pstore still
showed the older UFS trace, not a new V34-specific crash record.

The same boot passed phone-side V31 RAM health startup
(`logs/local-health-v31-ram-trial-1792584438241004578/result.json`), the
guarded handoff was armed
(`logs/v33-openrc-arm-1792584467168567897/result.json`), and independent
Alpine/OpenRC PID 1 verification passed:
`logs/v33-alpine-pid1-verification-1792584471170676275/result.json`.
**V33 is the current installed `boot_a`; Alpine is the last verified PID 1.**
The V34 diagnostic findings below remain useful but V34 must not be treated
as currently installed. Preserve V33 and the exact V19 rollback.

## Next diagnostic candidate — V35 health-only split prepared offline

V35 was built from exact V34 with **only the primary `/init` tail changed**.
It runs the same local Wi-Fi and V31 health startup, then keeps monitored
BusyBox PID 1 and rescue SSH for a maximum 600-second observation window;
it does not attempt the Alpine handoff. This separates a health-startup
failure from a handoff failure on a later controlled trial. The existing
startup failure paths still request power-off; a separate bounded timer
requests power-off after the successful observation window.

Image SHA-256:
`6deda6ecc63ce8b11fc882cbe7ebcc19ff8c4eae13e04c609fa15ac81e35036d`.
The private image and build receipts are under
`linux-port/artifacts/local-health-only-v35-offline/`. Independent offline
validation passed: exact stock kernel, unchanged supplementary payload,
primary init-only change, BusyBox syntax, local health fixture, AOSP AVB
model, and exact V33/V19 rollback hashes. **V35 has not been flashed or
tested on Lynx.** `tools/capture_v35_health_window.py --seconds 900` has a
pinned, dynamic-address read-only collector; its one-second dry run against
the current V33 boot correctly reported `candidate_seen=false`.
`tools/lynx_boot_a_v35_trial.py --prepare` passed and its flash/reboot modes
require a fresh collector and Fastboot identity check. The next trial needs
Noob to put Lynx in Fastboot on USB, then prompt USB removal after the reboot.
Restore V33 explicitly afterward; V35 has no automatic rollback write.

## Current status — V34 diagnostic retrial captured two incomplete boots

On 2026-10-21, Noob connected Lynx in Fastboot. Fresh identity and layout
preflight matched serial `89BYAY5L4T9HFUOV`, unlocked slot A, and the
recorded bootloader (`logs/fastboot-preflight-1792583578244697246.json`).
The guarded tool wrote V34 **only to `boot_a`** and rebooted separately:
`logs/v34-boot-a-trial-1792583597458126374/result.json` and
`logs/v34-boot-a-trial-1792583604061913647/result.json`. USB disappeared.
V33 was subsequently restored, as documented above. The exact V33 rollback
remains verified locally.

The dynamic pinned-key collector captured 14 raw snapshots at `.6` during a
420-second window:
`logs/v34-health-window-1792583593671638978/result.json`. Two distinct
boot IDs were observed: `9d5a4867-b49f-47e7-85d8-7f63f6ab5109` and
`5160d5a7-37d8-4df0-a0ad-71cf27c1339a`. Neither reboot was commanded by
Nexus. Both reached Wi-Fi and rescue SSH, started the local V31 health child,
identified the gauge, and loaded the battery monitor. The first reached the
cooling watcher; its last successful snapshot was at 109 seconds uptime with
28.8°C battery and 37.2°C reported cooling temperature. The second lost SSH
after 103 seconds uptime, while the health child was waiting for cooling.
Neither snapshot series showed `health-bootstrap/ready` or Alpine PID 1.
The precise reason for each loss of contact is **unproved**; do not label it a
thermal shutdown, kernel crash, or successful handoff without further logs.
The bounded collector saw no third contact. No recovery partition, slot B,
or bootloader changes occurred. Next physical step: enter Fastboot on USB,
verify identity again, restore V33 to `boot_a`, then boot V33 with the pinned
dynamic contact collector. Do not retry V34 unchanged.

## Current status — V33 restored; Alpine/OpenRC and both SSH ports live

On 2026-10-21, Lynx reappeared in Fastboot as serial `89BYAY5L4T9HFUOV`.
Fresh read-only preflight matched unlocked slot A, the recorded bootloader,
and partition sizes (`logs/fastboot-preflight-1792580315999550166.json`).
The exact previously successful V33 image was restored to **`boot_a` only**;
the guarded write receipt is
`logs/v34-boot-a-trial-1792580319529388222/result.json`. A separate Fastboot
reboot succeeded, after which USB disappeared. **V33 is the last image written
to `boot_a`.** Slot B, recovery foundations, and bootloader were untouched.

Because `.4` now has another host key, the new pinned-key collector
`tools/lynx_dynamic_pinned_contact.py` found Lynx at `192.168.100.6`, proved
V33 BusyBox identity, cancelled its fallback timer, and saved pstore and boot
log before health startup:
`logs/dynamic-pinned-contact-1792580356789565421/result.json`. The saved
pstore contains an older UFS-probe trace; it does **not** identify the V34
loss-of-contact cause. Do not infer that V34 crashed in UFS from it.

The same boot passed V31 phone-side health startup
(`logs/local-health-v31-ram-trial-1792580485087229192/result.json`) and the
guarded V33 handoff was armed
(`logs/v33-openrc-arm-1792580507021565090/result.json`). Independent verifier
`tools/verify_alpine_pid1.py` passed on boot ID
`c365645f-0351-4b6d-b612-4d62866a8d05`:
`logs/v33-alpine-pid1-verification-1792580602503990622/result.json`.
Alpine 3.24.2/OpenRC is PID 1 from persistent ext4 `userdata`; OpenRC started
`lynx-health`, `lynx-wifi`, and `lynx-dropbear`. The pinned rescue SSH on 22
and Alpine SSH on 2222 both answered at `.6`. The live health sample was
27.6°C battery, 100% capacity, and 36.3°C maximum thermal sensor, with three
cooling controls. This still requires a host-confirmed V33 boot and a RAM
health arm before Alpine handoff; autonomous cold boot remains unproved.

For a future V33 boot, start `tools/lynx_dynamic_pinned_contact.py --seconds
420` **before** Fastboot reboot, unplug USB promptly, then use its fresh
`result.json` as `--contact-receipt` for
`tools/launch_local_health_ram_trial_v31.py --run --usb-unplugged-confirmed`.
Use that health receipt with `tools/arm_v33_openrc.py --arm`, then
`tools/verify_alpine_pid1.py`. Keep the phone unplugged because charging under
native Linux is not yet validated.

## Current status — V34 booted BusyBox; Alpine/health unverified

On 2026-10-21, fresh Fastboot preflight matched Lynx's serial, unlocked slot
A, bootloader and partition sizes at
`logs/fastboot-preflight-1792578074717725713.json`. The guarded V34 tool
wrote **only `boot_a`** and later issued a separate reboot:
`logs/v34-boot-a-trial-1792578082487216310/result.json` and
`logs/v34-boot-a-trial-1792579249916028829/result.json`. Noob confirmed
USB removal. V33 was subsequently restored, as documented above; V33 and
V19 exact rollback images remain local.

The original collector's fixed address `192.168.100.4` answered with a
different SSH host key. It was rejected; the pinned known_hosts record was
not changed. A bounded local WLAN discovery found Lynx's exact pinned host
key at `192.168.100.6`:
`logs/v34-pinned-key-discovery-1792579355439307533/result.json`. One direct
SSH proof verified the V34 `/init` SHA, stock kernel, BusyBox hash and PID 1
as `/bin/busybox` on boot ID `f67d0c37-932b-4195-a194-6eb6ced80e42`:
`logs/v34-first-pinned-proof-20261021/result.json`. The next SSH attempt
timed out, and a repeat pinned-key discovery found no Lynx host. This could
be a safety power-off or network loss; **the cause is not proved**. There is
no evidence yet that V34 reached health-ready or Alpine PID 1. The first
dynamic-IP health collector saw no later Lynx contact:
`logs/v34-health-window-1792579502641247181/result.json`.

Noob reported a black screen and attempted one unplugged power-on. A fresh
pinned dynamic-IP collector ran its full 420-second window and captured
**zero** Lynx SSH samples:
`logs/v34-health-window-1792579759626634111/result.json`. The screen/power
state after that window is unconfirmed. This does not prove a kernel boot or
power-off on the second attempt. V33 restoration and first-boot pstore capture
are now recorded above. The pstore snapshot did not establish the V34 failure
cause. A future V34 trial needs `tools/capture_v34_health_window.py` running
before reboot so it can sample the live boot log as soon as pinned SSH appears;
keep the V33 rollback image and Fastboot recovery procedure ready.

## Current status — V34 autonomous Alpine candidate prepared offline

V34 was built from the hardware-booted V33 image. It combines local Wi-Fi
readiness, the previously live-tested V31 phone-side health startup, and the
V33 persistent Alpine PID 1 handoff using the guard's local authority.
The exact stock kernel and unrelated image members are preserved. Offline
build and independent validation passed; exact V33 and V19 rollback images
and a guarded Fastboot tool are ready. `tools/lynx_v34_contact.py` is a
pinned read-only collector that does not require a host arm marker. See
`LOCAL-ALPINE-V34.md` for architecture, SHA-256, receipts and limits.
This section records the earlier offline state; see the newer hardware trial
above. Charging remains unvalidated.

## Current status — Alpine SSH owned by OpenRC; Wi-Fi packages installed

On the V33 boot recorded below, signed Alpine Dropbear was installed in the
persistent root and verified over a separate pinned SSH connection on port
2222. The custom `lynx-dropbear` OpenRC service adopted the running daemon
and is enabled in the default runlevel. Rescue SSH on port 22 remained live.
Signed Alpine WPA and iproute2 packages were installed. Alpine `wpa_cli` did
not get a response from the existing rescue-stage WPA socket, while the
rescue-stage client confirmed an associated Noobia WLAN. The `lynx-wifi`
OpenRC service adopted that live connection without restarting WPA or DHCP,
and is enabled in the default runlevel. Its private configuration was copied
phone-to-phone into the persistent root with mode 0600; no secret contents
were logged. Alpine's native association/DHCP startup path is untested.
See `ALPINE-PID1-MILESTONE.md` for receipts and exact limits. No new boot
image was flashed after V33. Native networking and cold boot are unproved.

## Current status — native Alpine/OpenRC is PID 1 on Lynx

The V33 `boot_a` trial succeeded. Fresh Fastboot preflight matched the
expected serial, unlocked slot A and partition sizes. Guarded V33 write and
separate reboot receipts:
`logs/v33-boot-a-trial-1792445914513243332/result.json` and
`logs/v33-boot-a-trial-1792445920287863995/result.json`. USB was removed;
pinned V33 SSH reached `192.168.100.4` on boot ID
`be9f6a18-bfd6-444b-9dc0-cdf98c593e27`:
`logs/wifi-v19-contact-1792445911633295372/result.json`. The V31 RAM-only
health startup passed with battery 26.4°C and 98%:
`logs/local-health-v31-ram-trial-1792446026167719022/result.json`.
The live guard passed and the one-boot handoff marker was written:
`logs/v33-openrc-arm-1792446052738563577/result.json`.

PID 1 then executed Alpine `/sbin/openrc-init` from the persistent ext4
`userdata` root. The first capture is
`logs/v33-first-handoff-observation-1792446062978025910/`; a full pinned
same-boot verification passed at
`logs/v33-alpine-pid1-verification-1792446158439995141/result.json`.
OpenRC 0.63.2 started its `lynx-health` service; Wi-Fi SSH remained reachable;
Alpine 3.24.2, Python 3.14.8, Git 2.54.0 and a fresh phone-side health
sample passed. See `ALPINE-PID1-MILESTONE.md` for repeat steps, receipts,
rollback and limitations. **Current `boot_a` is V33; Alpine/OpenRC is the
last verified PID 1.** This is a host-supervised boot: autonomous health,
networking, SSH and charging still need development. Preserve the working
image and slot B/recovery foundations while this live session is used for
incremental Alpine services.

## Current status — V32 rescue online; PID 1 stdout root cause proved; V33 offline

V32 was written **only to `boot_a`** after a fresh Fastboot identity check:
`logs/v32-boot-a-trial-1792435399661704248/result.json`. The work session
paused before reboot, so the original listener expired without phone contact.
The next session confirmed Lynx still in Fastboot, started a fresh listener,
and issued the separate reboot:
`logs/v32-boot-a-trial-1792445533063206353/result.json`. Pinned V32 SSH
arrived at `192.168.100.4`:
`logs/wifi-v19-contact-1792445529418312899/result.json`. V31 RAM-only
health passed on this fresh boot; battery was 26°C and 97%:
`logs/local-health-v31-ram-trial-1792445642081177002/result.json`.

The live guard passed and the V32 one-boot marker was armed:
`logs/v32-openrc-arm-1792445655432146871/result.json`. V32's three PID 1
attempts all refused before any Alpine mount, then kept BusyBox rescue SSH.
Its new stderr log captured `sh: write error: Bad file descriptor` three
times. PID 1 has **no file descriptors 0 or 1**; only descriptor 2 exists,
pointing to V32's RAM stderr log. The guard's final success `echo` therefore
fails when invoked from PID 1, making its shell return nonzero despite the
checks passing. A pinned read-only experiment reproduced guard failure with
stdout closed and guard success after reopening standard descriptors in
tmpfs. Tool and durable proof:
`tools/probe_pid1_stdio.py`,
`logs/pid1-stdio-diagnostic-1792445807386439038/result.json`.

V33 is built **offline and unflashed** from the V32 image. It changes only
primary `/init` to reopen stdin from `/dev/null` and log PID 1 stdout/stderr
in RAM before the guard. The V32 stock kernel, supplementary payload,
bounded retry and other primary members remain identical. BusyBox shell
syntax, CPIO roundtrip and AOSP AVB model validation passed:
`linux-port/artifacts/persistent-openrc-v33-offline/validation.json`.
`tools/lynx_boot_a_v33_trial.py --prepare` passed with the exact independent
V19 rollback image. Current known `boot_a` is V32, last observed as BusyBox
rescue over pinned SSH. Alpine/OpenRC has **not** become PID 1. A V33 hardware
trial requires a fresh Fastboot USB connection, ready collector, guarded
`boot_a` write, and prompt USB removal after reboot. Keep slot B and
recovery-related partitions untouched.

## Current status — V29 BusyBox rescue online; V32 prepared offline

Noob put Lynx in Fastboot on USB for another Alpine trial. Initial read-only
preflight timed out because this new USB node lacked user access; a temporary
ACL was granted only to `/dev/bus/usb/001/010`, then fresh Fastboot checks
matched the expected serial, unlocked slot A, bootloader and partition sizes:
`logs/fastboot-preflight-1792431862062915667.json`.

The previously booted V29 image was written to **boot_a only** and rebooted:
`logs/v29-boot-a-trial-1792431870358045880/result.json`,
`logs/v29-boot-a-trial-1792431878041632365/result.json`. Fastboot USB
disappeared; pinned V29 native SSH appeared at `192.168.100.4`:
`logs/wifi-v19-contact-1792431866815671862/result.json`. V31 RAM-only
health started within the fresh window and passed, including a cooling
temperature wait; battery was 27°C and 80%:
`logs/local-health-v31-ram-trial-1792431985311055042/result.json`.

The live V29 guard passed and the one-boot RAM handoff marker was written:
`logs/v29-openrc-arm-1792432013795642673/result.json`. PID 1 then logged
`PERSISTENT_OPENRC_SAFETY_GUARD_REFUSED` at uptime 122.76 and stayed in
BusyBox rescue with SSH. At uptime 150 the exact guard passed manually;
no `userdata` mount was present. Thermal and battery watcher logs remained
healthy around the refusal. Captures are in
`logs/v29-second-handoff-diagnostics-1792432085858736986/`. The precise
guard refusal reason is still unknown because V29 did not save stderr.
Alpine/OpenRC has **not** become PID 1. Current known `boot_a` is V29 and
Lynx was last observed online by pinned SSH; no later partition write or
reboot occurred.

V32 is a private **offline, unflashed** candidate. It derives from V29 and
keeps V29's stock kernel and exact supplementary payload; only primary
`/init` changes to save guard stderr and retry at most twice after a clean
guard refusal. The retry fixtures cover transient, persistent, other-cause,
and partial-state outcomes. BusyBox syntax, member roundtrip, stock-kernel
identity and AOSP AVB model checks passed:
`linux-port/artifacts/persistent-openrc-v32-offline/validation.json`.
`tools/lynx_boot_a_v32_trial.py --prepare` passed with exact V19 rollback.
V32 has **not** been flashed or booted. A future bounded trial needs a new
Fastboot USB connection, fresh preflight, a ready listener, and Noob at the
cable for prompt USB removal after reboot.

## Current status — V19 SSH online and V31 cooling retry verified in RAM

Noob reported Lynx cool and in Fastboot with USB unplugged. After the prompt
to select Start, a fresh pinned listener verified V19 native SSH on boot ID
`c0bf91c1-f21b-4774-b059-7f0a0d702507` at `192.168.100.4`:
`logs/wifi-v19-contact-1792431105220440810/result.json`. The V31 RAM-only
health launcher ran within the fresh-boot window, completed its safety
handoff, verified active health, and cancelled its independent outer timer:
`logs/local-health-v31-ram-trial-1792431399506532376/result.json`. The
phone-side child log shows one clean cooling-watcher retry, so this fix has
been exercised on hardware. See `COOLING-STARTUP-V31.md`. No phone partition
was written; `boot_a` remains exact V19. Battery was 27°C and 80% at the
health postcheck. Keep USB unplugged for this boot.

A bounded read-only capture of the LK `expdb` prefix succeeded:
`logs/expdb-prefix-1792431426107805689/result.json`. Its SHA-256 is
identical to the earlier pre-V30 capture; the bounded comparison recorded zero
changed 4 KiB blocks at `logs/expdb-compare-1792431562652533086/result.json`.
It adds no V30 failure evidence.
An attempted pre-exec handoff fixture refused in preflight because its guard
script was absent from V19 RAM; it did **not** reach a mount or partition
write: `logs/persistent-openrc-live-preexec-1792431468513829689/result.json`.
Alpine/OpenRC has still not run as PID 1. Do not reflash just to repeat this
known preflight; use the existing V29 live fixture evidence or prepare an
updated, reviewed handoff candidate offline.

The frozen V29 handoff guard was separately staged in V19 RAM and sampled
20 times without arming PID 1. All 20 checks passed; observed CPU/SoC maxima
were 33.358–35.648°C. Tool and receipt:
`tools/probe_openrc_guard_live.py`,
`logs/openrc-guard-live-1792431613054634856/result.json`. This verifies the
guard on the current healthy boot, but does not identify the earlier one-time
V29 refusal or explain V30's absence of network contact.

## Newest status — second V19 boot briefly reachable, no health armed

After the health refusal below, Lynx became unreachable, then appeared again
over pinned V19 SSH with **new** boot ID
`63e473d6-64fd-45dd-b04b-b27928d22e88`. This proves a restart occurred;
it does not prove whether the preceding safety power-off completed. The new
boot had no health modules, no health-ready marker, charger `online=0`, and
`network-timing-start=0`. At uptime 249.20 it logged
`WIFI_HOST_CONTACT_DEADLINE; REQUESTING_ONE_SUPPORTED_BOOTLOADER_REBOOT`.
Its fresh-boot window for the RAM health trial had already passed, so no
health attempt or host acknowledgement was made on this boot.

While pinned SSH was available, read-only captures of `console-ramoops-0`
and `pmsg-ramoops-0` succeeded:
`logs/v30-followup-pstore-1792430568294370111/result.json`. They contain
the older diagnostic token `69adf9d14707d848063b861b8f248748`, not the
current V19 token. Their startup warning and call traces are therefore
not evidence of the V30 failure. No partition read or write occurred.
Lynx's current physical screen/power state is not confirmed; Noob has been
asked to leave USB unplugged and report whether she is off and cool.

## Earlier status — V19 reached SSH; health startup refused and phone became unreachable

Noob reported ready at the cable. The exact V19 rollback receipt was checked,
a fresh pinned listener started, and a new Fastboot preflight passed. A
separate Fastboot reboot succeeded:
`logs/v19-rollback-reboot-1792430115303041191/result.json`. The USB device
disappeared from the host, and V19 reached pinned native SSH on a new boot:
`logs/wifi-v19-contact-1792430103957361931/result.json`.

The RAM-only health bootstrap was started within its fresh-boot window but
**refused** because the cooling watcher did not become ready. The retained
stream shows CPU/SoC readings around 40.0–40.5°C during startup and a
26.9°C battery sample. The earlier read-only <40°C precheck evidently passed,
but the watcher startup guard did not remain true; this is a possible timing
race, not proven to be the sole cause. Receipt and full stream:
`logs/local-health-ram-trial-1792430224336258363/`. The launcher saw no
working health supervisor and sent a safe power-off request. That SSH request
timed out; an independent 300-second phone-side power-off timer had already
been armed. Subsequent TCP/22 was unreachable and no phone USB device was
present. **Do not claim confirmed power-off** without a physical observation.
No expdb or pstore read was attempted after the health refusal.

`boot_a` remains the exact V19 restoration from the preceding status. Stop
native trials until the phone is confirmed cool and off, then address the
cooling-watch startup race and repeat a bounded rescue boot before any new
Alpine candidate. The general thermal hold remains active.

An offline V31 RAM-only cooling startup retry is prepared and fixture-tested;
see `linux-port/docs/COOLING-STARTUP-V31.md`. It has not been run on Lynx.

## Earlier status — V30 did not contact; V19 restored, Fastboot held

The V30 pinned listener reached its 600-second deadline with **zero**
beacons and no verified SSH:
`logs/wifi-v19-contact-1792429267778777426/result.json`. V30's BusyBox
stage and Alpine handoff were not observed; the cause remains unknown.
Lynx later reappeared on USB as MediaTek Fastboot device `0e8d:201c`.
Fresh read-only Fastboot preflight again matched serial, unlocked slot A,
bootloader and partition sizes:
`logs/fastboot-preflight-1792429891155934733.json`.

The guarded rollback wrote **only `boot_a`** with the exact known V19 image;
Fastboot reported OKAY for send and write:
`logs/v30-boot-a-trial-1792429894066810273/result.json`. Lynx remains in
Fastboot and **has not been rebooted after restoration**. No other partition
or slot was changed. If Noob wants the V19 BusyBox SSH rescue online again,
coordinate a separate Fastboot reboot and immediate USB unplug. Do not
attempt another Linux flash until V30's no-contact failure has been
investigated. Host kernel USB history shows the V30 Fastboot USB device
disconnected at 20:01:22 local time and a new Fastboot device appeared at
20:05:18; this alone does not show whether Lynx booted a kernel in between.

## Earlier trial — V30 flashed and rebooted without network contact

Noob put Lynx in Fastboot on USB. Fresh Fastboot preflight passed and the
guarded tool wrote **only `boot_a`** with V30 SHA-256
`0159029d4a20322766544f3785e992c93b456fcbbbe8b386671ecbb73bc491c7`.
Fastboot reported OKAY for send and write; receipt:
`logs/v30-boot-a-trial-1792429270975536236/result.json`. A separate guarded
Fastboot reboot succeeded at
`logs/v30-boot-a-trial-1792429281904579912/result.json`. USB was removed:
the phone's USB device disappeared from the host. The pinned listener is
`logs/wifi-v19-contact-1792429267778777426/result.json`. At approximately
341 seconds after listener start, it had received **zero** beacons and no SSH
connection. The Nexus Wi-Fi interface and router were reachable, so host
network failure was not evident. The phone's screen state was not reported.
The <240-second window for the RAM health bootstrap passed, so Alpine was
not armed. The listener was allowed to reach its deadline before the V19
rollback described above. Do not claim V30 booted or that the V30 retry ran;
neither has been observed.

## Earlier status — V29 booted, BusyBox rescue online; V30 prepared offline

Noob confirmed USB was unplugged after the guarded Fastboot reboot. V29
booted its BusyBox stage and reached pinned native SSH at `192.168.100.4`
(`logs/wifi-v19-contact-1792428703198572812/result.json`). The RAM-only
health bootstrap passed and remains active
(`logs/local-health-ram-trial-1792428823716659703/result.json`). The fresh
V29 identity and live handoff guard passed before the one-boot RAM marker was
written (`logs/v29-openrc-arm-1792428896405236024/result.json`).

At uptime 171.85 seconds, PID 1's own guard refused the transition and V29
entered its deliberate BusyBox rescue loop. Pinned SSH, health watchers and
the same boot ID remained available. A subsequent manual guard check passed;
25 further read-only checks passed with no refusal. V29 did not capture the
transient refusal reason, so the exact cause is unknown. Preserve the
first-run logs at `logs/v29-first-handoff-diagnostics-1792428944458381344/`
and the guard recheck at `logs/v29-guard-recheck-1792428965407013661/`.
Alpine/OpenRC has **not** become PID 1. The current boot is useful rescue;
do not claim a successful Alpine boot.

V30 is an offline V19-derived candidate that records guard refusal output
and retries only that guard failure up to three times at five-second
intervals. Its image SHA-256 is
`0159029d4a20322766544f3785e992c93b456fcbbbe8b386671ecbb73bc491c7`.
The exact V19 parent, stock kernel, CPIO roundtrip, shell syntax and AOSP
AVB model passed at
`linux-port/artifacts/persistent-openrc-v30-offline/validation.json`;
the real retry function also passed transient and persistent failure fixtures
(`tools/test_persistent_handoff_retry_v30.py`). **V30 has not been flashed or
booted.** The general thermal hold remains active; a new bounded trial needs
a scoped exception, fresh recovery checks, and Noob at the cable for the
Fastboot reboot. Current V29 BusyBox/SSH should be used for any further
read-only diagnostics without restarting Lynx.

## Earlier status — V29 written to boot_a, before the first reboot

Noob put Lynx in Fastboot on USB. Fresh read-only preflight matched serial
`89BYAY5L4T9HFUOV`, product `k6983v1_64`, unlocked slot A, bootloader
`k6983v1_64_45ca337_202308100614`, and expected partition sizes:
`logs/fastboot-preflight-1792427448588958908.json`. Scoped access was
granted only to USB node `/dev/bus/usb/001/006` (group `plugdev`). A pinned
fast-contact listener started at
`logs/wifi-v19-contact-1792427460653526462/result.json`. The guarded tool
then wrote **only `boot_a`** with V29; Fastboot returned OKAY for sending and
writing the exact 64 MiB image. Receipt:
`logs/v29-boot-a-trial-1792427464188884820/result.json`.

Lynx **has not been rebooted** after this write; last observed mode is
Fastboot, and no V29 runtime claim is justified yet. Wait for Noob to be at
the cable before issuing the separate reboot, because USB must be unplugged
for the native trial. The active listener may expire and should be restarted
if it is no longer `listening` with a fresh heartbeat. V19 exact rollback is
ready via `tools/lynx_boot_a_persistent_openrc_trial.py --restore-v19` after a
fresh Fastboot preflight. No other partition or slot was changed.

## Earlier status — V29 persistent-root handoff prepared

At this point, V19 was still the live `boot_a` image and BusyBox was still PID 1. The persistent
Alpine root has passed a guarded live pre-exec trial through the read-write
mount, exact root-file hashes, all four bind mounts, native Python chroot and
final health check. The fixture replaced only the final `exec` with unmounts;
no PID 1 change or boot image write occurred. A private V19-derived V29
host-armed boot candidate is built and independently checked offline. Its
image hash is `2483ba8d5ee43ef2ba692885682b9ebacc59fdb8216700eaad1eff7c531b3048`.
See `PERSISTENT-OPENRC-HANDOFF.md` for receipts and the remaining hardware
trial boundary. The next physical trial needs Fastboot over USB, fresh identity
checks, a ready pinned network collector, and verified stock `boot_a` undo.
The general Linux-flash thermal hold remains active because V29 still depends
on host-assisted health startup. No Fastboot action has been requested yet.

## Newest status — 2026-10-19 persistent Alpine root

The approved first-GiB Alpine 3.24.2 ext4 install on `userdata` succeeded.
On-phone full readback SHA-256 matched the source and a read-only handset mount
confirmed Alpine release and OpenRC init. The install receipt is
`logs/userdata-ext4-install-1792420775526722662/result.json`; details and
rollback pointers are in `PERSISTENT-ALPINE-FIRST-GIB-TRIAL.md`. Afterward,
pinned SSH still proved the same V19 BusyBox boot ID
`3990a1d8-963d-4d17-972e-b0b8a7b366e6`, ready health supervisor, and
unmounted `userdata`. BusyBox remains PID 1; no automatic Alpine handoff or
boot image change was attempted. Continue with a guarded handoff and preserve
V19, stock recovery images, slot B, and the original first-GiB backup.
The Alpine root's missing `/dev`, `/proc` and `/sys` mount-point directories
were then created and verified on Lynx. Python and Git ran from the persistent
root in a temporary read-only chroot with `/dev` bind-mounted. The post-fix
first-GiB hash and receipts are in the persistent Alpine trial document.
The persistent root now also has the reviewed OpenRC health adoption service
enabled in its default runlevel. A guarded read-only live probe passed with
all four virtual-filesystem mounts, Alpine Python/Git/procfs, and complete
mount cleanup. OpenRC has not replaced BusyBox PID 1; trying `rc-service`
before that handoff was correctly refused by OpenRC. The service install,
failed diagnostic, and corrected probe receipts are in the same trial document.

## Newest status — 2026-10-17

The human most recently reported Lynx in Fastboot, then confirmed she is not on
USB. Without the cable there is no live device query. The last guarded identity
listener expired with no phone contact; no partition, slot, boot image, or phone
power state was changed by that attempt. Offline development can continue, but a
device-side test will require a later connection and a fresh identity check.

Offline progress: Alpine 3.24.2 ARM64 with signed OpenRC 0.63.2-r0 now boots as
PID 1 under QEMU using the exact frozen V19 stock kernel, reaches a test service
in the default runlevel, and powers off cleanly. The six signed package APKs
replay offline, and a second QEMU test passes the BusyBox-to-OpenRC PID 1
handoff from the exported 4.5 MB rootfs while keeping a pre-existing worker
alive. The inert archive fits inside V19's supplementary payload budget by
measurement; no updated image was built. Evidence and repeatable tools are in
[ALPINE-USERSPACE.md](ALPINE-USERSPACE.md). These remain VM/size-only results;
no OpenRC image has been booted on Lynx. Keep V19's proven Wi-Fi/SSH startup
and separately validated battery/thermal watchers as prerequisites for any
future handoff; cold-boot watcher startup still needs verification.

Goal remains native Linux on OnePlus Nord 3 CPH2493 / MT6983, with a minimal
BusyBox boot first. User permits recoverable controlled boot_a trials and broader
judged-safe recovery work. Do not infer that an offline test guarantees hardware
success. Preserve working bootloader/recovery foundations and slot B.

User clarified that a bare **OK** may mean the application showed its additional
cybersecurity-content notice and interrupted the reply. Treat it as continuation
of the existing authorized task, not new authorization, a state change, or a
request to evade safeguards. The exact notice and official help page were checked.
General loader-bypass investigation was paused; ordinary Linux image diagnostics
continue. No authentication bypass or exploit payload was executed.

Button timing and outcomes are in `BUTTON-SEQUENCES.md`. A plain unplugged/off
USB connection missed the handshake. Probe-confirmed waiting plus both volume
buttons held at the explicit connect-NOW signal reached regular OPLUS Preloader,
accepted stock DA1/DA2 into RAM, and answered the short-filename availability
request. No AIO file data followed. Successful session:
`tools/mtk-sessions/aio-readiness-1791650798290665979/`.

Last observed USB state: 22d9:0006 OPLUS Preloader, stock RAM loader potentially
awaiting the deliberately unsent file. No host probe is still running. Buttons
have been released at Aria's instruction. The next native trial requires a
physical reset and return to Fastboot, not reuse of this RAM session.

Persistent boot_a was successfully restored to verified August stock image:
`logs/boot-a-usb-device-mode-trial-1791645217241106203.json`.
No later partition flash has been issued. Matching stock vendor_boot_a, dtbo_a,
vbmeta_a restoration receipt remains valid; slot B was preserved.

A concrete native USB omission was found: xhci-mtk-hcd.ko missing before MTU3
creates its enabled host child and saves its driver's pointer. Exact stock-module
disassembly supports the pointer conversion lacking a null-driver check. This
is a plausible startup fault, not an observed cause of the phone's failure.

Corrected offline image:
`artifacts/busybox-August-usb-device-xhci/nord3-busybox-candidate.img`,
SHA256 6ec551d5f4742fdb6c06d5e5f012ef934fa8663d0010fb7957bee3d81242e5d9.
Exact unchanged stock kernel, 35 matching modules, xHCI before MTU3, and a guard
withholding MTU3 if xHCI did not load. Target ARM emulation reached an interactive
shell and loaded all 35 modules; 13 peripheral-mode guards passed. Upstream AVB
unlocked/locked models and independent packaging validation passed their expected
checks. Physical Linux boot/USB binding remain unproven. Metadata retains original
OEM hash with a modified-payload mismatch; OEM approval is not claimed.

Fixed tool: `tools/lynx_boot_a_usb_xhci_trial.py`.
Default offline readiness verified exact stock undo and trial commands; receipt:
`logs/boot-a-usb-xhci-trial-1791652260685692785.json`.
Once user returns Lynx to Fastboot, identify the new USB node and provide scoped
access, then fresh preflight and the authorized boot_a-only trial may proceed.
The tool's `--flash-linux --reboot` writes only boot_a and reboots once.
Observe for native USB/serial success; if it fails, restore stock boot_a through
Fastboot. Stop for unexpected recovery behavior. Do not run another stored Linux
variant without a concrete new fix or diagnostic purpose.

## Latest change: corrected xHCI trial ran

The user reached Fastboot via recovery-first/Volume Down + Power, with USB
initially unplugged. After plugging in, host node 001/014 was 0e8d:201c; access
was granted and fresh identity/slot/size preflight passed. The corrected native
image was written to boot_a and rebooted successfully:
`logs/boot-a-usb-xhci-trial-1791652936719946783.json`.
The 60-second USB observation showed no phone endpoint or ttyACM:
`logs/lynx-usb-observation-1791652951320637469.json`.
No physical native boot is proved. This supersedes the earlier current-state
statements: Lynx has left the RAM-loader session; the corrected Linux candidate
is now the last recorded boot_a write. Stock undo is pending Fastboot return.
The next operation is fixed-tool `--restore-stock` after fresh USB/preflight,
without reboot, before another trial.

A possible later non-bypass diagnostic lead is the preloader's ordinary READ32
interface. The captured target reports Mem read auth false, but that alone does
not prove the command is implemented or accessible. Its upstream entry-point
must not be run if it automatically invokes a bypass. Only a separately reviewed,
fixed-region, bounded direct-read path could test this lead. No direct READ32
probe has been prepared or executed in the current work.

## Latest stock undo and next prepared diagnostic

User returned quickly to Fastboot, node 001/015, 0e8d:201c. Fixed tool verified
stock undo and fresh identity/slot/size checks, then restored boot_a successfully:
`logs/boot-a-usb-xhci-trial-1791653164047994118.json`.
No reboot or other partition write followed. Last persistent boot_a is stock
again; the corrected native candidate is no longer the last write. Log export:
`logs/pllk-1791653196269209324.json`. Current last observed mode is Fastboot.

An ordinary fixed-region header probe is now prepared:
`tools/lynx_preloader_pstore_header.py`. Default is offline plan; `--self-test`
checks fixed address/word encoding and six protocol failure cases. `--connect`
waits for regular MT6983 preloader, verifies the chip ID against the successful
earlier Lynx session, requires Mem read auth false, then sends one 16-word read
at 0x48090000 (64 bytes). Both status fields must be zero, with exact word count.
It blocks all loader uploads, watchdog/register/memory/storage writes,
authentication, BROM resets, bypasses and fallback memory reads. No CLI generic
reader or full dump is invoked. Waiting is bounded to 180 seconds; active work
to 30 seconds after handshake. No live header read has occurred yet.

Next physical step: unplug USB and use the official Power + Volume Up
10-second force-off sequence, leaving USB unplugged. Once the user is ready,
start the guarded header probe with necessary USB access and wait for its actual
waiting output. Signal connect NOW while both volume buttons are held, without
Power; release buttons only after confirmed acquisition. This repeats the
recorded successful loader-entry combination, with an ordinary diagnostic read
instead of any loader upload or bypass. If read permission/status is denied,
stop without changing security policy or supplying a payload.


## Full pstore collector prepared (2026-10-10)

User requested complete acquisition and preserved evidence to reduce repeated physical cycles.

The new tool `tools/lynx_preloader_pstore_capture.py` requests exactly the known pstore RAM allocation at `0x48090000`, length `0xe0000` (917504 bytes), through a single ordinary READ32 transaction. MT6983 regular preloader mode, the previously recorded exact SOC_ID, memory-read authorization flag, and pinned diagnostic source hashes are checked before the request. Loader uploads, authentication, security bypass, register/memory/storage writes and fallback routines remain blocked. Protocol commands necessarily travel over USB; they are read requests, not memory writes.

The capture stores raw big-endian wire words, decoded little-endian memory bytes, protocol replies, numeric leading/trailing statuses, request echoes, per-fragment timing, SHA256 hashes and partial results. A fragmented final word remains in the raw file and is recorded separately. The SDK aggregate reader can discard partial replies on timeout, so the transfer uses direct bounded endpoint reads. This is an application-level capture, not a complete USB bus trace. Handshake console output is preserved separately.

Twelve offline cases passed, including full-region capture, fragmented replies, accepted low nonzero statuses, rejected leading/trailing statuses, interrupted body and completion reads, three failed echo stages, and an oversized response. All mock session artifacts are retained in `tools/test-artifacts/pstore-offline-tests-1791659269535613359/`, with machine-readable `test-results.json` and source hashes.

No live run of this full collector has occurred. Hardware support for this single large request is unproven. A rejected request ends without another technique. Successful transport would not establish pstore age, decode compressed records, or prove association with the failed native boot.

Lynx currently enumerates as 22d9:0006, USB 001/017, from the earlier interrupted header request. Its protocol state is not assumed clean. A fresh physical preloader entry is required before live acquisition. No new flash or partition change was made during collector development. Last known persistent boot_a remains the verified stock undo recorded in logs/boot-a-usb-xhci-trial-1791653164047994118.json.


### Earlier header probe correction

The earlier live header session `tools/mtk-sessions/pstore-header-1791654123980651167/` completed the regular MT6983 handshake and exact chip identity match, then stopped on a nonzero leading status before saving any header. The numeric status was not preserved. The pinned upstream implementation accepts statuses 0 through 255; the original probe incorrectly required zero. Therefore its “denied” error is not evidence of confirmed authorization denial. The new collector records the actual status, uses the documented range, and never falls back to authentication or bypass.

The immediately preceding both-volume-button attempt from an active restart loop entered Fastboot instead. A later recovery-menu Power off, unplug, then both-volume-button connection reached OPLUS Preloader. These are distinct initial states; the combination is not guaranteed to select the same mode from every state.


## Full collector first live attempt

Session pstore-full-1791659369491056067: USB was absent before starting the probe. After the explicit connect cue, the user held both volume buttons and USB enumerated 001/018, 22d9:0006 OPLUS Preloader. The regular handshake never completed; repeated handshake failures were observed. Stopped verified PID60882 with SIGINT; process exit130 and receipt state stopped/KeyboardInterrupt. No fixed-region memory request, loader upload, authentication, bypass or partition write occurred. This combination reached Preloader but did not prove a fresh protocol state or a completed handshake. Detailed exceptions were hidden at the current logging level, so enabling preserved DEBUG logging before another attempt. USB remained connected after the user was instructed to release buttons.


## Ordinary pstore read result — 2026-10-10

The DEBUG attempt pstore-full-1791659570169672293 enumerated USB001/020 (22d9:0006), but startup synchronization received A0 instead of expected5F. Stopped PID61573 with SIGINT, exit130. Same physical connection then accepted a single ordinary GET_HW_CODE query (fd09070000); normal preloader identification matched MT6983 and the exact saved Lynx SOC_ID. This establishes that the connected phone was already command-ready, without authentication, bypass or loader upload.

Full-region READ32 (917504 bytes) and a separate 64-byte size check at 0x48090000 both echoed every request field exactly and returned leading status0x1000 before data. No RAM data was received. Receipts and raw protocol replies are in tools/mtk-sessions/pstore-full-1791659786746018581/ and pstore-full-1791659923281277745/. Consolidated evidence: docs/pstore-ordinary-read-result.json. The MTKClient status table names0x1000 CRYPTO_INIT_FAIL, but this generic label does not prove the exact proprietary preloader cause or justify authentication/bypass. Ordinary RAM access to this region is unavailable through the tested interface; stop repeating it without new evidence.

ModemManager was active and inspected the same ttyACM path. Scoped mmcli inhibition failed NotFound, leaving service state unchanged. Interference was not established as the cause. No background collector remains, no partition changed, and last persistent boot_a remains stock. User was told to release volume buttons and leave USB connected.


## Separate stock AEE log-export lead

See docs/STOCK-AEE-DUMP-LEAD.md for new offline AEE command registration and destination dispatch. USB output exists, but the default command can select ext4 output; no command issued. Normal-LK and AEE analyses are saved separately. Prepared guarded getvar-all inventory; next required interaction is return to Fastboot, USB connected. No background collector or modem-service inhibition remains.


## Native software-reboot proof completed; stock undo done

The controlled test produced an automatic Fastboot return with the exact reboot-mode signature requested by the native Linux init. This is strong hardware evidence that native userspace executed, not a working USB/Linux installation or a captured native console marker.

Prepared image: artifacts/busybox-August-boot-proof-bound-guards/nord3-busybox-candidate.img, SHA256 a9a72334185a5ddec9b6e3ece6e9e01600582f62c4db7bebc8ce87c4d5c3fe43. Exact August stock kernel; native BusyBox PID1; matching mtk_wdt, reboot-mode and syscon-reboot-mode drivers; one freestanding ARM64 RESTART2 bootloader request only after actual driver/node/property checks. It does not start the USB gadget stack or write partitions. Preliminary artifact busybox-August-boot-proof is retained separately.

The ARM64 helper executed under the exact stock kernel in QEMU and the kernel printed Restarting system with command bootloader, exiting QEMU successfully: artifacts/emulated-reboot-helper-1791662465537639804/result.json. The exact full image plus vendor-before-generic ramdisk refused the reboot on virtual hardware and remained PID1: artifacts/emulated-boot-proof-guard-1791662599378418727/result.json. Eleven exact-source host guard cases passed: tools/test-artifacts/boot-proof-guard-1791662566283189527/result.json. An initial fixture path substitution also changed the driver name; this test-only bug was fixed, and the failed artifacts were retained. Independent image and AOSP unlocked/locked AVB checks passed: docs/boot-proof-validation.json. AOSP AVB is not OnePlus LK.

User's existing boot_a-only native-trial authorization applied. Stock undo hash, matching baseline and exact restore command were checked before flashing. Trial accepted only boot_a and one reboot: logs/boot-a-boot-proof-trial-1791662841074803432.json. No other partition, slot or bootloader change. User was told to leave buttons untouched. USB changed from original Fastboot001/021 to absent, then returned as new Fastboot001/022. The first observer expired shortly after reboot; the second found Fastboot, so exact return latency was not captured.

Pre-trial log: logs/pllk-1791661502886412997.clean.txt. NONRST_REG2=0x20000000, low mode bits0; ramconsole watchdog status0. Post-trial log: logs/pllk-1791662950347665197.clean.txt. NONRST_REG2=0x28002003, low mode bits3; ramconsole watchdog status0x2; long-pressed reboot0; LK boot mode99. Mode3 matches the actual stock FDT mode-bootloader property. The log's raw rst-from-lk label remains and is preserved; this minimal init omitted OEM boot-stage-reporting modules. No physical native console text was retrieved. Hardware interpretation remains explicitly indirect. Consolidated evidence and limitations: docs/boot-proof-hardware-result.json.

After saving reset evidence, verified stock boot_a undo succeeded with no reboot: logs/boot-a-boot-proof-trial-1791662962729666883.json. Last persistent boot_a is stock; Lynx is in Fastboot, with no observer/probe running. Native proof image is preserved locally. USB serial/networking and a usable native OS are still unproved.

The earlier serial-verification warning was inspected in stock LK. The mismatch path returns an error and the caller logs then joins its normal continuation. No halt or forced Fastboot was found on that local failure path; no device identity data changed. Stock boot.img has a1650580-byte generic ramdisk, and the saved Nord3 board configuration does not declare separate init_boot use. Its partition's existence alone was not evidence that boot_a was the wrong trial target.

Next focused investigation: compare native USB/module bringup with this three-driver baseline. The candidate no longer needs to be judged only by USB enumeration: the standard software-return proof provides another observable result. Keep the original USB image, all proofs and stock restore intact. No additional trial is currently running.


## Follow-up reset-handler review and pending experimental detail

The ordinary `reboot` literal is suffix-merged into another string, explaining the first failed pointer lookup. Actual registration references locate normal reboot handler at analysis0x106cb4 and reboot-bootloader handler0x106ce0. The normal handler acknowledges then calls platform reset with1,1; it has no explicit mode3 setter. The bootloader handler explicitly passes3 to its mode setter then resets with1,7. Evidence: docs/lk-reboot-string-references.json and lk-fastboot-reboot-handlers.disassembly.txt. This strengthens the controlled native-init interpretation; complete proprietary reset graph remains unproved.

Asked the user whether any buttons were pressed after the no-buttons instruction and before Fastboot return; reply pending. This is an experimental observation check, not a new permission request. Do not equate a bareOK popup-continuation reply with a button-state confirmation. Current phone remains stock boot_a in Fastboot, node001/022; no trial or observer runs. Preserve proof artifacts and prepare USB/module comparison only after accounting for this control detail.


## Human observation confirmed; BusyBox first

Noob explicitly confirmed that no buttons were touched and Lynx was in Fastboot after the trial. This closes the pending experimental-control question and strengthens the native-init software-reboot proof. On the next turn Noob requested that the result be documented and coding continue, then clarified BusyBox first. Current development milestone is a live BusyBox USB shell using the already compatible stock kernel; kernel rebuilding and distribution integration follow specific demonstrated needs. No new flash is authorized by mere build-tool output; existing scoped controlled-trial authorization and restoration checks continue to govern any trial.


## BusyBox USB-console coding and first trial

Current milestone is a live BusyBox shell over USB, using the proven exact August stock kernel. No kernel rebuild, Android framework, distribution root filesystem, networking or SSH was added in this step.

The successful minimal reboot proof, source and result are preserved unchanged. Noob confirmed no buttons were touched during that return to Fastboot. The project README now points to that result and the current BusyBox milestone; the previous README is archived as README-BEFORE-CONFIRMED-BOOT.md.

New native source: init-busybox-usb-console. New reproducible offline builder: build_busybox_usb_console.py. Image: artifacts/busybox-August-busybox-console/nord3-busybox-candidate.img; SHA2563c75e5791fa9ed6be1a655e978fac4c68b8ea1479ca4777b54106f51326572dc. It retains the exact stock kernel and matching vendor ramdisk dependency, loads the proven reset drivers first, then the preserved USB supplier order. All37 module hashes and versions match stock. It exposes only ACM serial, with USB1d6b:0104 and serial lynx-busybox. A shell connection prints native banner, uname, PID1 information, module progress and full kernel dmesg. PID1 persists after shell exit. Runtime mounts are proc/sysfs/tmpfs/configfs; no partition mounting or native partition-writing tool is included.

The exact proven driver/property guard is embedded before the USB code. If USB setup reports failure and the reset guard passed, init requests one standard software return to Fastboot. If the guard did not pass, init stays alive without a reboot request. A kernel/module-probe hang or apparently bound gadget that never enumerates may still require physical Fastboot entry; automatic recovery is not guaranteed.

The stock-kernel ARM64 VM test executed the exact combined vendor/generic image, observed native PID1, USB setup failure and RESET_GUARD_REFUSED, with no reboot request. Artifact: artifacts/emulated-busybox-console-1791666814527661557/result.json. Independent fixed-image, module/order and unlocked/locked AOSP AVB checks passed in tools/validate_busybox_usb_console.py; report docs/busybox-console-validation.json. These tests do not establish a hardware USB shell.

Host recorder tools/lynx_busybox_console.py matches only the native USB IDs and serial before opening ttyACM. It preserves raw bytes and partial captures, waits for the native banner, then sends only uname/PID1/id checks. Completion parsing was tested against fragmented data and echoed commands so command echo cannot count as a successful reply. Capture has a120-second deadline and32MiB size bound. It emits a heartbeat and process identity; the trial tool refuses a Linux write if the recorder is not actively waiting. Stock restoration does not depend on a recorder being active.

Trial tool: tools/lynx_boot_a_busybox_console_trial.py. Verified offline readiness: logs/boot-a-busybox-console-trial-1791667156051355831.json. It preserves exact Fastboot identity/slot checks, verified firmware/baseline checks and stock boot_a undo. Longer passive observer: tools/lynx_usb_observe_busybox.py, duration180seconds, starts before the trial.

Live trial boot-a-busybox-console-trial-1791667291915431284 accepted only boot_a and one reboot. User was told USB connected, no button presses. Recorder: logs/busybox-console-1791667287110999263.json. Observation: running at time of this entry. Hardware result remains pending. Last persistent boot_a is this console candidate until its verified stock undo is recorded; do not assume the prior stock undo is still the last write. No other partition, slot, bootloader, calibration or authentication change occurred.


## First BusyBox USB-console result: no banner; stock undo pending

The boot_a write and reboot succeeded: logs/boot-a-busybox-console-trial-1791667291915431284.json. Native console recorder reached its120-second deadline with zero captured bytes and no shell marker: logs/busybox-console-1791667287110999263.json. User reported OrangeState afterward. No usable BusyBox USB shell is proved. Screen alone does not locate the failure or establish whether the native kernel is running. The previous minimal software-reboot proof remains valid and unchanged.

Last persistent boot_a is the BusyBox console candidate, not stock. Stock undo is pending physical Fastboot return; user was instructed to return to Fastboot with USB connected. Exact stock undo is ready in tools/lynx_boot_a_busybox_console_trial.py --restore-stock, which does not require a live console recorder. No further image trial before undo and new diagnostic evidence. Consolidated result: docs/busybox-console-first-hardware-result.json. Longer passive observer remains bounded to180seconds; the native console collector has exited.

Next code investigation should separate module loading, peripheral-role selection, gadget binding and host enumeration into observable checkpoints using the successful software-return baseline. Also fix the success criterion: a successful UDC bind without host enumeration currently leaves init waiting for ttyGS0; it cannot be treated as a successful console or guarantee an automatic return. Preserve this first image and its evidence before changing that behavior.

## Console undo complete; timed driver checkpoint started

Lynx returned physically to Fastboot on USB001/023. Verified stock boot_a
restoration succeeded without reboot: logs/boot-a-busybox-console-trial-1791667721697489275.json.
The first console failure record now includes that restoration receipt.

Noob reiterated that timing must always be considered. This is preserved in
/noobia/lynx/AGENTS.md. All new code/artifacts stay under Lynx; prior proof,
console image, source and captures are preserved unchanged.

New offline builder: linux-port/prepare_busybox_diagnostics.py. It prepares
separate suppliers-only and with-MTU3 module checkpoints from the exact proven
BusyBox image. Each requires actual reset-driver guards before loading more
modules, stops on any insertion error, then rechecks guards and requests one
standard Linux bootloader reboot. No gadget, role change or mdev is included.
The separate console source draft adds a bounded host-configured-state check;
it has not been built or flashed.

Six shell fixtures passed: tools/test-artifacts/busybox-usb-checkpoints-1791667910990513433/result.json.
Both exact checkpoint images reached native PID1 and refused hardware-dependent
work in QEMU with no reset devices. With-MTU3 VM receipt:
linux-port/artifacts/emulated-module-checkpoint-with-mtu3-1791667912949232589/result.json.
Independent validation passed: linux-port/docs/usb-module-checkpoint-validation.json.
Three passive observer fixtures passed: tools/test-artifacts/trial-observer-1791668080105103084/result.json.

One with-MTU3 boot_a-only diagnostic was issued under the existing controlled
trial authorization after fresh preflight and verified stock undo. User was
told to leave USB connected and avoid buttons. Before-trial supported raw LK
log: logs/pllk-1791668092698085859.json. Trial:
logs/boot-a-usb-checkpoint-trial-1791668099832373363.json. Image SHA256:
5bb984899b19c9e739faa23aa9039374a5ad20ab99c10948d5d2b964da3616d6.
The image write and single reboot succeeded; last persistent boot_a is now
this checkpoint, superseding the stock restoration above. No other partition
was written. Stock undo is pending after observation.

The passive USB collector starts and confirms readiness after preflight and
immediately before the write, in the same process, so approval latency does
not consume the observation window. It persists wall times, monotonic elapsed
times, USB node changes and heartbeat. Trial records both command start/end
times and raw Fastboot replies. Observer:
logs/usb-checkpoint-observer-1791668099992342633.json. At first status check,
USB departed at1.766 seconds after collector start; no return was yet observed.
Observation is bounded to180 seconds after reboot and was running at this entry.
Do not treat a return alone as complete proof: fresh identity/reset evidence
and human button observations still matter. A missing return cannot identify
the failing module or distinguish insertion failure from a probe hang.

## Driver-only hardware checkpoint: bounded negative result, hands required

The full180-second window after reboot completed. No Fastboot return, native
gadget or recognized preloader endpoint was observed after the initial USB
departure. Trial process exited0 because commands and observation completed;
its explicit fastboot_return_observed field is false, so process exit0 is NOT
a successful module-loading or native-console result. Evidence:
docs/usb-module-checkpoint-first-hardware-result.json. This does not invalidate
the earlier confirmed three-module BusyBox boot proof.

Last persistent boot_a remains the with-MTU3 checkpoint. Verified stock undo
is pending physical Fastboot return. User was told to return to Fastboot with
USB connected; work stopped for that physical interaction. No observer or
trial process remains running. On return, obtain fresh node access/identity
checks, capture the supported read-only LK reset log if Fastboot behaves as
expected, then run tools/lynx_boot_a_usb_checkpoint_trial.py --restore-stock.
Do not reboot after undo. Preserve all evidence and review the reset log
before another trial. The suppliers-only checkpoint and enumeration draft
were not flashed.

## Checkpoint stock undo complete; original boot inference reviewed

User returned Lynx to Fastboot USB001/024. Supported read-only LK log export
succeeded: logs/pllk-1791668359166049762.json. Verified stock boot_a restoration
then succeeded without reboot: logs/boot-a-usb-checkpoint-trial-1791668366401102943.json.
Last persistent boot_a is stock. No trial/observer remains running. Other
partitions and slotB were not changed. After-checkpoint log has NONRST_REG2
0x20000000 and ramconsole watchdog0; no useful crash location or mode3 software
return signature was retrieved. Physical reset history can erase evidence,
so absence of a marker is not proof native init never ran.

Noob asked whether the earlier automatic Fastboot test was certain. Reviewed
the original receipt: only normal fastboot reboot was sent; the controlled
return had no reported button input and mode changed from0 to3 with software
reset0x2. Those are strong indirect evidence for native execution. There was
no direct native console marker, the exact return timing was missed, and the
complete proprietary fallback/reset graph remains unproved. Earlier wording
claiming definite execution was too strong. README and original result now
explicitly distinguish strongly supported execution from conclusive proof.
Next causal verification should pair a fully timed minimal-baseline repeat
with an otherwise matching hold/no-reboot control, or capture direct native
output. Do not describe the failed USB/module checkpoints as disproving the
original evidence or as locating the hardware failure.

Matching hold/no-reboot control prepared OFFLINE at
artifacts/busybox-minimal-hold-control/nord3-busybox-candidate.img, SHA256
25040803f00546bda46ba58407f19e7dcf1978375466a210df360cbcdd2f9166.
The sole changed archive entry is init: its guarded reboot request is replaced
by a hold-control message. Kernel, modules and unused helper remain identical
to the minimal reference. Four exact guard/branch fixtures passed with reboot
stubbed: tools/test-artifacts/boot-hold-control-1791668614253554039/result.json.
No hardware causality is established by these tests. Control is not flash
eligible, has not been flashed, and would require physical Fastboot recovery
after observation. Lynx remains on restored stock boot_a in Fastboot; no further
phone command was issued after the original-evidence confidence review.

## Timed minimal comparison: reboot arm repeated; hold arm observing

Two fixed tools now preserve the reviewed boot_a-only trial guards, fresh
preflight, matching stock firmware and exact undo checks, and same-process
timed USB collection: tools/lynx_boot_a_timed_minimal_reboot_trial.py and
tools/lynx_boot_a_timed_minimal_hold_trial.py. Receipts include image/tool/observer
hashes, command wall times and monotonic durations. Complete hold image passed
independent archive comparison, source branch tests, exact-stock-kernel QEMU
guard refusal and unlocked/locked policy checks:
docs/boot-hold-control-validation.json. Only init changes; unused helper remains.

Reboot-arm trial: logs/boot-a-timed-minimal-reboot-trial-1791668852862284083.json.
USB observer: logs/usb-minimal-reboot-observer-1791668853023049484.json.
Original image returned again as Fastboot001/025, approximately21.624 seconds
after normal reboot began (poll resolution0.25seconds). Before/after supported
LK logs: logs/pllk-1791668845978416528.json and logs/pllk-1791668922230977251.json.
Reset mode again changed0x20000000 to0x28002003 and watchdog status0 to0x2.
Stock boot_a undo then succeeded without reboot:
logs/boot-a-timed-minimal-reboot-trial-1791668928584614474.json.
User was instructed to avoid buttons/cable changes. A specific asynchronous
button/cable observation question is pending; do not infer confirmation.

Hold-arm trial: logs/boot-a-timed-minimal-hold-trial-1791668942994926109.json.
Its boot_a write and one normal reboot were accepted. Passive observation is
bounded to180seconds after reboot. User was told to leave buttons/cable untouched.
Last persistent boot_a is NOW the minimal hold control, superseding the undo
above. Stock undo after this control remains pending. No other partition or
slot was changed. A return would challenge the native-init attribution; no
return supports the contrast but cannot itself prove native init reached hold.
Do not declare conclusive native PID1 proof without direct output or stronger
causal evidence. Collation tool: tools/summarize_minimal_boot_comparison.py.

## Timed minimal comparison complete; physical undo required

Reboot arm returned as Fastboot001/025 about21.624seconds after normal reboot
began and reproduced mode3/software-reset0x2. The matching hold arm had no
recognized phone USB endpoint or Fastboot return for the full180-second
post-reboot observation. Both collectors and trial processes have exited.
Machine-readable collation with raw receipt hashes, command-relative event
timings, reset-log values and limits: docs/timed-minimal-boot-comparison.json.

This contrast strengthens the native-init interpretation if buttons/cable were
untouched. The positive-arm specific human observation question remains
pending; no answer was inferred. Hold-arm input confirmation is not yet
recorded. No direct native console marker was captured, and no-return alone
cannot show the hold init actually reached its hold. Conclusive native PID1
proof remains false in the saved result.

Last persistent boot_a remains the minimal HOLD CONTROL, not stock. User was
instructed to return Lynx physically to Fastboot with USB connected; work stops
for this interaction. On return: verify new USB node/ACL and fresh identity,
capture supported reset log if normal Fastboot behavior permits, then restore
only verified stock boot_a with
tools/lynx_boot_a_timed_minimal_hold_trial.py --restore-stock, no reboot. Preserve
all captures. Do not run another trial before this undo is recorded.

## Hold-control stock undo completed

User returned Lynx physically to Fastboot USB001/026. New-node ACL completed,
fresh identity checks passed, and supported read-only reset log was saved:
logs/pllk-1791669338064161970.json. Verified stock boot_a restoration accepted
without reboot: logs/boot-a-timed-minimal-hold-trial-1791669344703570332.json.
Current last persistent boot_a is STOCK, superseding the hold control. No
observer/trial runs. Machine-readable comparison now includes this undo and
after-hold log. Preserve outstanding button/cable observation uncertainties;
a bare go did not answer them.

Next offline preparation will split the previously failed34 additional-module
sequence at dependency-complete prefixes, preserving the same checkpoint init
and kernel. This is targeted localization after a negative full-sequence test,
not evidence that any particular driver failed.

## Dependency-checked prefix localization: halfway returns

Offline builder linux-port/prepare_usb_module_prefixes.py prepared prefixes
5,17,26 from the failed full checkpoint, changing ONLY the module-list entry
in the archive. Init, kernel, other entries and metadata tail remain identical.
All prefixes passed independent dependency-order, stock hash/version, archive
comparison and unlocked/locked policy checks. Prefix17 exact image reached
native PID1 and refused hardware work in QEMU without real reset devices:
linux-port/artifacts/emulated-module-prefix-17-1791669497528573254/result.json.
This VM refusal also covers identical init in the other prefixes; those two
images were not independently emulated. Reports: docs/usb-module-prefix-*-validation.json.

Prefix17 boot_a-only trial and one reboot were accepted:
logs/boot-a-usb-prefix-17-trial-1791669578567730520.json. Observer recorded
Fastboot001/026 departure and return as001/027:
logs/usb-prefix-17-observer-1791669578729142671.json. User reported OrangeState,
then explicitly FASTBOOT; no specific no-button/cable confirmation was supplied.
Supported post-trial LK log reproduced NONRST_REG2=0x28002003 and watchdog0x2,
with raw reset-stage label lk retained: logs/pllk-1791669638160806380.json.
Verified stock boot_a undo accepted without reboot:
logs/boot-a-usb-prefix-17-trial-1791669721794768324.json.

Next authorized timed checkpoint prefix26 was issued after that undo:
logs/boot-a-usb-prefix-26-trial-1791669772716713000.json. It adds nine subsequent
modules and excludes the last eight. No userspace gadget/role setup is added.
User was instructed to leave USB/buttons untouched. Consult its operation
receipt for write/observation status; if accepted, it supersedes stock undo
above and requires another verified stock undo. Consolidated localization:
docs/usb-module-prefix-hardware-results.json. Prefix5 has not been flashed.

Prefix26 returned as Fastboot001/028 without a new physical-entry instruction.
Observer: logs/usb-prefix-26-observer-1791669772877163869.json. Supported reset
log again showed mode3/software-status0x2, raw stage lk retained:
logs/pllk-1791670042485253427.json. Stock boot_a undo succeeded without reboot:
logs/boot-a-usb-prefix-26-trial-1791670056875302215.json.

The preserved suppliers-only image (33 additional modules, no MTU3) passed
the same independent prefix validator after an explicit path/hash mapping
was added. Fixed tool: tools/lynx_boot_a_usb_prefix_33_trial.py. Authorized
timed boot_a-only trial issued:
logs/boot-a-usb-prefix-33-trial-1791670069077804262.json. If its write is
accepted it supersedes the prefix26 stock undo. User was instructed to leave
USB/buttons untouched. A prefix33 return compared with the previous full34
failure narrows the problem to adding MTU3 or that addition's effects on the
guard/reset path; it still does not capture a kernel crash or prove its cause.

Prefix33 returned as Fastboot001/029. Supported reset log again matched mode3
and software-reset0x2: logs/pllk-1791670188040507900.json. Verified stock boot_a
undo accepted with no reboot: logs/boot-a-usb-prefix-33-trial-1791670202862845876.json.
Current last persistent boot_a is STOCK; no trial/observer runs. Prefix5 was
not flashed. The boundary is now adding MTU3 to the33-module support sequence;
the precise hardware failure mechanism is still unknown.

Stock kernel config uses MODVERSIONS, full Clang LTO and strict CFI, compiler
Android clang12.0.5 r416183b. Module signing is unset. The local kernel repo
is shallow and does not contain the stock311738fbb5a8 object, so an arbitrary
source rebuild is not yet a verified compatible module.

An OFFLINE experimental NULL-child-driver guard was prepared in a separate
stock MTU3 copy. It changes only the three instructions at text0x54d0..0x54d8:
direct driver load fromx0, preserve zero return, CBZ to the existing cleanup
branch when no child driver is bound. Module SHA256
49688170d2be04c5051331f93ddf8eda8d8bc5ce37baf82dd04d2edb7f657223;
original d3c59fa794a6e02f014dd0de660592bb66c9d7f8eb941c1d1183f8a3322bb467
is preserved. Manifest: artifacts/mtu3-null-child-guard/manifest.json.
All other bytes, imported symbol versions, relocations and CFI-related sections
remain byte-identical. ELF build-id is retained, so SHA256/manifest must be used
to identify the changed artifact. The source-equivalent guard breaks on an
unbound child, matching the machine-code early exit rather than continuing to
another child; an initial draft needed this semantic correction.

Six extracted ARM64 fragment cases passed in exact-stock-kernel QEMU:
artifacts/emulated-mtu3-null-guard-1791670531833079574/result.json.
They demonstrate the original NULL-to-negative-pointer construction and the
guard's NULL/non-NULL/return behavior, not an actual MT6983 crash. A further test
adds actual original-module load/unload and guarded-module load under the stock
kernel; result pending at this entry. The separate full checkpoint image
substitutes only lib/modules/mtu3.ko, leaving init, kernel, module order and all
other archive entries intact: artifacts/busybox-mtu3-null-guard-checkpoint/
with SHA256c815d527d6a4ff54f4ef2e04f968a7e4a6cf0a51e6e2eb1bba33df3e411c7c6c.
It is offline and not yet flash eligible. No guarded module/image has been
sent to Lynx. Independent validation and actual module-load testing are required
before a controlled trial of this specific guard.

## Guarded MTU3 trial: offline checks pass, hardware return fails

Original-module load, unload and guarded-module load all succeeded under the
exact stock kernel in isolated QEMU. The six ARM64 arithmetic/branch/store
cases also passed in that run:
artifacts/emulated-mtu3-null-guard-1791670663767994158/result.json.
Independent image/module delta and unlocked/locked policy checks passed:
docs/mtu3-guard-checkpoint-validation.json. An applicable source patch and
guarded source are preserved separately as source-null-child-guard.patch and
mtu3_host.guarded.c under artifacts/mtu3-null-child-guard; the earlier manual
source-equivalent draft is retained too. No kernel/module authentication or
CFI settings were changed; the guard modifies existing function instructions.

Authorized boot_a-only checkpoint accepted one image write and normal reboot:
logs/boot-a-mtu3-guard-trial-1791670823185473386.json. Passive observer:
logs/usb-mtu3-guard-observer-1791670823343810265.json. The full180-second
post-reboot window ended with no Fastboot return or recognized phone endpoint.
Both processes exited. User reported OrangeState, then a further reboot into
OrangeState. Exact screen-reboot timing was not measured; do not invent it.
The NULL-child guard is NOT a demonstrated hardware fix. No direct native
console or kernel crash location was captured.

Last persistent boot_a is the GUARDED MTU3 CHECKPOINT, not stock. Verified stock
undo is pending physical Fastboot. User was instructed to return Fastboot with
USB connected; work stops for that physical step. On return, grant the new
node ACL, wait for completion, verify fresh identity, save supported read-only
LK reset evidence, then run tools/lynx_boot_a_mtu3_guard_trial.py --restore-stock
with no reboot. Preserve other partitions and slotB; stop on unexpected recovery
behavior. Consolidated result: docs/mtu3-guard-first-hardware-result.json.

Future diagnostics should distinguish a failed/blocked insmod, changed reset
guard, and kernel fault before another fix is selected. A supported userspace
supervisor after the confirmed prefix33 may help distinguish completed insertion
from a blocked loader through bounded, timed software-return outcomes. Do not
implement another hardware trial before stock undo and reset-evidence review.

## Guard experiment stock undo complete; supervise the loader next

Lynx returned physically to Fastboot USB001/030. Fresh identity checks and
supported read-only reset log export succeeded: logs/pllk-1791671229069563463.json.
Verified stock boot_a restore then succeeded without reboot:
logs/boot-a-mtu3-guard-trial-1791671243113551814.json. Current last persistent
boot_a is STOCK. No observer/trial remains running. After-log shows mode0 and
watchdog0 without useful crash location; physical reset history can erase
prior evidence, so this is not proof that the experimental kernel never ran.

Next offline diagnostic source is mtu3-timed-supervisor.sh. It runs the original
stock MTU3 insertion in a child after the returning prefix33 and validated
stock reset bindings. Parent observes15seconds, then makes one supported reset
request at20seconds (success),40seconds (returned error), or60seconds (no result
within15seconds) after child start. Runtime state is tmpfs; no partitions are
mounted or written. It deliberately avoids re-enumerating potentially blocked
platform sysfs after the child starts. Timing is an indirect beacon: only
interpret with calibration, untouched controls and matching reset evidence.
Kernel/power faults or a blocked reboot path can still prevent all beacons.
This source is offline, untested, not built into a candidate and not flashed
at this entry. Test child status, timing/clock failure, single-reset semantics
and independent artifact compatibility before considering hardware use.

## Stock-module MTU3 supervisor validated and trial started

Six exact-source host cases passed with simulated clock/reboot stub: success
deadline20, returned-error deadline40, pending child deadline60, and clock or
mount failures with no reset call. Evidence:
tools/test-artifacts/mtu3-supervisor-1791671516955331219/result.json.
Built image: artifacts/busybox-mtu3-timed-supervisor/nord3-busybox-candidate.img,
SHA256adb55ffe21b8079c4e64a8eb48917c6566dcfd58763fa813bb10a635ad2b6b9a.
Only init and module-list archive entries differ from the full stock-module
checkpoint. Original stock MTU3 and every other module remain unchanged; the
experimental pointer guard is NOT used. Parent loads the returning prefix33,
validates reset bindings, then forks the MTU3 load and uses RAM-only result state.
It does not re-enumerate platform sysfs after child start, avoiding that source
of blocking. It makes one supported restart request, never retries.

Exact image/stock-kernel QEMU refusal passed:
artifacts/emulated-mtu3-supervisor-1791671678612938593/result.json.
Independent archive/kernel/source/module integrity and unlocked/locked AVB
checks passed: docs/mtu3-supervisor-validation.json. Fixed trial tool:
tools/lynx_boot_a_mtu3_supervisor_trial.py, with verified stock undo and fresh
Fastboot checks. One authorized boot_a-only trial issued:
logs/boot-a-mtu3-supervisor-trial-1791671793516438825.json.
User was instructed to leave buttons/USB untouched for the full observation.
If the write succeeds it supersedes the guard-trial stock undo and requires
its own undo. No other partition, slot, module authenticity setting or CFI
setting changes. Observe this receipt before acting on current device state.

Timing interpretation is indirect. Child-relative deadlines20/40/60 correspond
roughly to earlier baseline reboot-return latency plus those delays, with
integer-uptime scheduling and USB polling uncertainty. Do not assign an outcome
from an overlapping or unexplained time. Kernel faults, reset-path blocking or
human input can prevent or confound every timing beacon. Preserve raw records
and corroborating reset signature before reporting a likely loader outcome.

## Supervisor return recorded; resumed after gap and stock undo complete

Saved observer recorded departure from Fastboot001/030 and return as001/031
83.693seconds after observer start, approximately82.106seconds after normal
reboot began. This is about60.48seconds beyond the prior21.62-second baseline,
consistent with the supervisor no-result-within15seconds /60-second deadline.
It is INDIRECT classification only: no child status text was captured, no
specific no-button/cable confirmation arrived, and result-publication failures
or intervening input can confound it. It does not prove a permanent hang.

User resumed work after token/context interruption. The host USB enumeration
now shows Lynx as001/004, not the historical001/031; do not use the current
enumeration as proof of the historical return or assume nothing happened in
the intervening gap. Current fresh identity checks match the device. Supported
LK log saved much later: logs/pllk-1791742954764056400.json. It now shows neutral
reset mode0x20000000 and watchdog0, with no software-return signature. This
cannot corroborate the historical timing beacon.

Verified stock boot_a restore succeeded without reboot:
logs/boot-a-mtu3-supervisor-trial-1791742981981876985.json. Current last persistent
boot_a is STOCK; no observer/trial remains running. Consolidated evidence and
limits: docs/mtu3-supervisor-first-hardware-result.json. Continue offline review
of MTU3 probe/initialization waits; do not promote timing inference into direct
native console proof or a located kernel fault. All old artifacts stay preserved.

## Real BusyBox test catches missing /dev/null; earlier hang inference invalid

Native supervisor VM test failed in a useful way:
artifacts/emulated-mtu3-supervisor-native-1791743705299181179/result.json.
The real ARM64 ash printed "can't open '/dev/null': No such file or directory"
at background-child startup and then selected the no-result timing path. The
handset supervisor inherited the minimal checkpoint init, which also mounted
fresh tmpfs /dev and created only console/kmsg, with no mdev scan or null node.
Thus the old82-second signal cannot establish that insmod ran or was blocked;
the child could fail BEFORE insertion. The earlier mocked BusyBox commands did
not reveal this. User was told clearly; no new phone write occurred.

Supervisor source now creates /dev/null c1:3 before forking. Host fixtures add
a null-node-creation failure case and keep success/error/pending/clock/mount
cases. Retest the actual BusyBox/stock-module VM success path before building
or flashing a corrected candidate. Preserve the defective historical image and
its receipts; do not reinterpret them as MTU3 hang evidence. Prefix33 versus
full34 foreground tests remain separate evidence of the MTU3-loading boundary.
Current last persistent boot_a is still restored STOCK, Fastboot001/004.

## Corrected supervisor v2 verified and authorized trial started

Corrected source819bf6ffe549e2137e682f5dfdb9e9eb0ff4abd1c35824781316c7f52826b29c
creates /dev/null before async ash child launch. Seven host cases passed:
tools/test-artifacts/mtu3-supervisor-1791743965836557432/result.json.
Actual ARM64 BusyBox with exact stock kernel and original MTU3 registered the
module and took the success reset path20.61s after child start in QEMU:
artifacts/emulated-mtu3-supervisor-native-1791743964645690671/result.json.
This is VM execution, not a captured Lynx shell or MT6983 hardware probe.

V1 trial tool is retired to restore-stock only; original source/tool/validator
archives retained in artifacts/busybox-mtu3-timed-supervisor. V2 image SHA256
382e6f6d82f249d8e51b29a0680aaabdc7bf48c506fcdc9d74ec68f1fec66832. Exact
v2 image refuses hardware-module work without real reset drivers in QEMU:
artifacts/emulated-mtu3-supervisor-v2-1791744222861099194/result.json. Independent
validator checks original kernel/module bytes, two-entry archive delta, source,
all test receipts and unlocked/locked AVB model: docs/mtu3-supervisor-v2-validation.json.

Read-only pretrial LK log: logs/pllk-1791744599163403308.json. V2 trial accepted
boot_a write and one normal reboot: logs/boot-a-mtu3-supervisor-v2-trial-1791744614133186620.json.
Observer is running; CURRENT LAST PERSISTENT boot_a is v2 diagnostic, stock undo
pending. No other partition changes. User told USB/buttons untouched. Do not
classify until observer result and timely LK reset evidence are collected.

## Corrected v2 hardware observation complete: no return; physical Fastboot needed

V2 trial1791744614133186620 accepted boot_a and normal reboot. Passive observer
1791744614291014500 recorded departure and no Fastboot return during the full
180-second post-reboot window; no observer errors. It provides NO timing outcome
classification, no captured child status and no direct native-userspace proof.
Summary: docs/mtu3-supervisor-v2-first-hardware-result.json. Current last persistent
boot_a is V2 DIAGNOSTIC; STOCK UNDO PENDING. No other writes, slots unchanged.
No active trial remains. Physical Fastboot return is required before read-only
LK capture and stock boot_a restoration without reboot. Stop hardware work and
ask user for that interaction; do not silently assume restored stock.

## Physical Fastboot recovered; v2 stock undo accepted

User reported Fastboot; USB001/006 0e8d:201c freshly verified. Read-only LK log
logs/pllk-1791744893648656623.json preserved before undo. Neutral NONRST_REG2
0x20000000/watchdog0 and volume-down key detection/mode99 reflect physical
return; no native crash or software-return proof. Verified STOCK boot_a write
accepted WITHOUT REBOOT: logs/boot-a-mtu3-supervisor-v2-trial-1791744900526607787.json.
Current last persistent boot_a is STOCK; no active observer. Recovery foundations
and slot B unchanged. Continue offline diagnosis before further trial.

## RAM-only registration guard prepared; independent tests; new trial started

User permits simultaneous tests when they do not collide. Offline VM runs use
separate artifact directories; handset operations remain sequential. No agents
spawned. New approach uses sysfs driver_override to block MTU3 matching before
platform probe, keeping original module bytes, CFI, kernel and DTB unchanged.
Guard scans compatible properties, permits only exact August USB0/USB1 OF nodes,
refuses bound devices or preexisting overrides, validates all targets before
writing, writes only driver_override, verifies readback and never unbinds.
This matching restriction exists in RAM only until reboot; no target partition
mount/write inside initramfs. Failure returns74 before insmod.

Exact August DTB + published platform source audit:
docs/mtu3-driver-override-audit.json; reference source commit81ec42ad5e803be0cba619f9f7bb298db7d33d7b
is related, not verified exact stock commit. Stock MTU3 .init.text disassembly
shows only __platform_driver_register call before return; module untouched.
Real stock-kernel driver_override write/read/clear on an unbound virt device:
artifacts/emulated-platform-driver-override-1791745084847200395/result.json passed.
Seven real ARM64 BusyBox guard fixture cases including bound/bad-second refusal:
artifacts/emulated-mtu3-registration-guard-1791745167330526009/result.json passed.

First combined VM test placed synthetic fixtures under /run, then supervisor
mounted fresh tmpfs there, hiding them. Preserve failure:
artifacts/emulated-mtu3-registration-supervisor-1791745272091483690/result.json.
It correctly refused insertion and took error reset at40.83s; NOT a passed
registration test or hardware fault. Corrected VM fixtures live at /fixture:
artifacts/emulated-mtu3-registration-supervisor-v2-1791745291349064983/result.json
passed, original module registered, child-relative reset20.57s. No MT6983 probe
is emulated. Exact handset image VM refuses work absent real watchdog drivers:
artifacts/emulated-mtu3-registration-image-1791745229591886300/result.json passed.
Independent image/source/module/AVB tests: docs/mtu3-registration-validation.json.

Candidate artifacts/busybox-mtu3-registration-only/nord3-busybox-candidate.img
SHA256 ed01113dbd38f98f41138dbecd3022217ce85bd163c1e394d41428960ae744c0.
Read-only pretrial LK: logs/pllk-1791745366907714303.json. Authorized boot_a trial
logs/boot-a-mtu3-registration-trial-1791745375231056769.json. Inspect receipt for
write/observation results; stock undo needed if write accepted. Preserve all
other partitions and slot B. This is timing inference, not a native shell.

## Registration-only hardware return: strong indirect success; stock undo complete

Trial1791745375231056769 accepted boot_a + normal reboot. Passive observer
1791745375391481368 recorded001/006 departure and001/007 return 41.803s
after normal reboot, about20.179s beyond minimal reference21.624s,
consistent with20s success deadline. Read-only LK1791745461052613061 captured
software-reboot signature NONRST_REG2=0x28002003 /wdt=0x2, raw stage=lk retained.
Pretrial LK1791745366907714303 was neutral0x20000000/wdt0. User explicitly said
no button presses; cable changes not separately explicitly addressed. This is
strong indirect native BusyBox/guard/stock-module-return evidence, not a captured
shell, device UDC binding, or conclusive native execution proof. Unblocked v2
did not return in180s; blocking controller matching restores the timed return.

Stock boot_a undo accepted WITHOUT REBOOT:
logs/boot-a-mtu3-registration-trial-1791745484785635273.json. Current last
persistent boot_a=VERIFIED STOCK; USB001/007 Fastboot. Other partitions/slot B
unchanged. Consolidated evidence: docs/mtu3-registration-first-hardware-result.json.
Next isolate which controller attachment/initialization path prevents return.

## Wi-Fi + SSH preparation in progress; no Wi-Fi handset flash yet

User/Rose prioritize native Wi-Fi+SSH and permit independent simultaneous tests.
Network selected=Noobia WPA2 (Nexus192.168.100.106 on wlx40a5ef5f66f1); M40 network
postponed explicitly. Existing saved profile UUIDdfa26e16-06b4-4746-95fd-4ad3bbc57f63
was read privately by tools/prepare_noobia_wifi_credentials.py. No password printed;
private config and dedicated client/host keys in /noobia/lynx/secrets mode0700.
Never print/cat these secrets or include them in diagnostic logs. Keys are pinned
with HostKeyAlias=lynx /secrets/lynx_known_hosts. Wi-Fi image must be mode0600
because it contains PSK-equivalent and SSH host key. Do not include client
private key in handset image. Host Wi-Fi configuration has not been changed.
User reported network drop; inspection found both host links UP and phone still
Fastboot001/007. Git broad source read suffered a network reset; no phone Wi-Fi
was flashed or tested. Current last persistent boot_a remains VERIFIED STOCK.

Matching local OTA vendor_dlkm,odm_dlkm,vendor,odm extracted and full operation/
partition SHA verified in artifacts/stock-cph2493-August-eu-ota/wifi-reference;
extraction-1791745920155667500.json. Vendor_dlkm is ext4, vendor/odm EROFS.
Read-only EROFS tool unpacked under tools/erofs (no host package install).
Initial debugfs rdump ownership changes were denied, contents existed; final
module provenance/byte/ABI checks still required. tools/audit_wifi_modules.py
combines modules.dep with embedded modinfo dependencies spanning boot/DLKM;
Wi-Fi graph55 modules. External module scmversion differs from kernel SCM
normally; exact vermagic and module_layout CRC/shared import CRCs match.
tools/audit_wifi_boot_modules.py adds read-only storage support:61-module graph,
23MB raw, no shared CRC conflicts; docs/wifi-boot-module-audit.json. Radio startup
may require additional OF clock/regulator suppliers beyond symbol dependencies.

Official Alpinev3.22 signed ARM64 musl,wpa_supplicant2.11,iw6.9,Dropbear2025.88
packages under tools/alpine-aarch64. Verifier/keys bootstrapped from HTTPS official
CDN in tools/alpine-bootstrap; apk verifies subsequent repository/package
signatures (initial missing trust-key extraction corrected; no allow-untrusted).
No host install. Absolute bin/sh symlink package excluded from root extraction;
keep proven static BusyBox shell. network_userspace.py packages native tools.
Actual ARM64 key-authenticated Dropbear loopback command +supplicant/iw under
exact stock kernel passed: artifacts/emulated-native-network-userspace-1791746685214260818/result.json.
DHCP initial fixture lacked full veth peer setup and DHCP server; failure preserved
at emulated-native-dhcp-ssh-1791747592558697513. Corrected VM uses signed full
iproute2 +dnsmasq only in isolated guest; DHCP+SSH passed:
artifacts/emulated-native-dhcp-ssh-v2-1791748020799825150/result.json. No radio verified.

Published module repo reference files preserved in docs/wifi-source-reference.
Stock driver readiness GET_CHIP_ID ioctl0x8004c200 returns direct integer0x6983.
/dev/wmtWifi WR-BUF:NVRAM prefix12bytes followed by factory payload requires one
complete write; data copied into driver RAM. Station command S powers Wi-Fi.
Factory file used by stock helper=/mnt/vendor/nvdata/APCFG/APRDEB/WIFI. Native
code must read existing data, not invent/rewrite calibration. read-only script
lynx-calibration-readonly.sh discovers sole PARTNAME=nvdata from sysfs, blockdev
sets RAM read-only flag, mount ext4 ro,noload, verifies ro, copies WIFI128..32768
bytes to RAM and unmounts. Fastboot getvar nvdata/nvram sizes returned EMPTY
(success status only; not geometry proof): logs/wifi-calibration-layout-1791747916677798142.json.
Runtime discovery must refuse ambiguous/absent partition. No writable mounting.

Native helper lynx-wifi-control.c/entry.S freestanding ARM64, no partition-write
paths; permits chip query, existing NVRAM/stock config RAM submit, station mode.
Initial BSS-only ELF helper segfaulted in VM BEFORE any handset use; archived
in artifacts/wifi-native-helpers/initial-helper-before-data-anchor.elf and source.
Synthetic calibration VM showed real block read-only /ro,noload mount/copy passed,
helper startup failed: emulated-native-calibration-readonly-1791748298212428796.
Corrected helper has nonempty writable .data mapping; retest currently running
(exec session54117). Do not use helper unless actual stock-kernel VM tests pass.
Final Wi-Fi boot image NOT YET BUILT OR FLASH-ELIGIBLE. Need supervisor/pstore
diagnostics, immutable image validation, native helper/RO safety tests and host
collector ready before controlled boot_a-only Wi-Fi trial. Preserve all proven
images and stock undo; slot B/recovery foundations unchanged.

## First Wi-Fi hardware trial ACTIVE: v3 two-stage boot_a installed

All work remains /noobia/lynx. Current final candidate=busybox-wifi-ssh-twostage-v3
SHA2563a1c2ddacac0c6fdf7e152a2db30add1b1b4fbab881346d6d346faf584abf94c.
Kernel bytes remain exact stock. Small first-stage ramdisk1615060 bytes fits
stock metadata boundary21889024; local VBMETA1600bytes/footer unchanged.
Supplementary native files stored ONLY in unused boot_a padding at25165824
(24MiB), gzip10195226bytes. SHA25622882fa431be1282b15b58d89e86247c027be7392f906199537b5df9c82b893b.
Do not mistake prior size failure for missing compression: existing codec already
uses LZ4 HC12. Actual constraint was the small stock loaded-area/metadata boundary.
Whole boot_a remains64MiB; no partition resized, no vendor_boot/dtbo/vbmeta/slot B
changes. Candidate/ramdisk/supplement private mode0600 in folder0700. Client
private key excluded. .gitignore excludes secrets and Wi-Fi artifacts.

Stage0 reset guards copied from known-returning prefix33. It creates /dev/null,
RAM /run128MiB, pstore/devpts; loads base33 +6 matching storage drivers from
unchanged vendor ramdisk. Waits up to30s for async UFS boot_a GPT discovery.
Child discovers unique boot_a64MiB, sets its block RO flag, reads fixed bounded
supplement, verifies SHA256 before gzip/CPIO extraction into RAM. First-stage
parent enforces180s deadline and one standard Fastboot request on failure.
After verified extraction, native Wi-Fi runtime starts with empty base/storage
load lists (already loaded); radio dependencies additional48, original stock
module bytes. Reads factory nvdata RO/noload, copies calibration to RAM; native
helper sends fixed documented /dev/wmtWifi RAM protocol; station, nl80211 WPA2,
DHCP, key-only Dropbear, public nonce beacon to Nexus192.168.100.106:5514.
Second parent deadline240s, cancelled only by token acknowledgement written
through pinned authenticated SSH. No extra reset attempt after helper returns.
Pstore warm-retention hardware unverified; complete diagnostics captured over
encrypted SSH when available. Public UDP discovery is NOT treated as proof.

Read-only calibration and corrected native helper test passed:
artifacts/emulated-native-calibration-readonly-1791748592634210034/result.json.
DHCP+key SSH+UDP native stock-kernel VM passed:
artifacts/emulated-native-dhcp-ssh-udp-1791749522460166466/result.json.
Actual bounded BOOT_A read-only +SHA+CPIO extraction on synthetic64MiB loop
device, wrong SHA/ambiguous partition refusal passed:
artifacts/emulated-native-boot-payload-1791752193887838856/result.json.
Ten parent supervisor control fixtures passed:
tools/test-artifacts/wifi-supervisors-1791752500321885348/result.json.
This test caught malformed no-newline host-confirmation causing early return
without fallback; v3 ignores it and continues deadline. Earlier v1/v2 image
artifacts retained, NEVER flashed. Exact final image VM reset guard passed:
artifacts/emulated-wifi-image-1791752848494401208/result.json. Independent source/
archives/modules/firmware/private-file/layout/AVB checks passed:
docs/wifi-image-validation.json. tools/validate_wifi_image.py pins exact hash.

New host collector tools/lynx_wifi_contact.py self-tests passed. It accepts only
image-specific public nonce from Noobia subnet, then requires pinned ED25519
host identity + dedicated client key +native kernel/PID1/init/BusyBox hashes.
After proof, sends atomic RAM acknowledgement and saves boot/wpa/pstore/kernel
logs privately. Listen process exec43967, receipt:
logs/wifi-contact-1791753503241750200/result.json. ACTIVE for600s since before
flash. New fixed trial tools/lynx_boot_a_wifi_trial.py checks collector freshness
and host IPv4; starts passive USB observer AFTER fresh preflight before write.
Trial exec14417, logs/boot-a-wifi-trial-1791753511523909231.json. BOOT_A write
and normal reboot ACCEPTED. Current last persistent boot_a=V3 WI-FI DIAGNOSTIC,
STOCK UNDO PENDING unless pinned native SSH succeeds. Trial observes USB/SSH up
to600s. No other phone commands issued during observation. User told buttons/USB
untouched. Read-only pretrial LK logs/pllk-1791753461116999900.json.

On successful pinned SSH/ack: keep native image running, collect diagnostics,
report true native communication. On returned Fastboot: fresh node ACL +LK log
then tools/lynx_boot_a_wifi_trial.py --restore-stock WITHOUT REBOOT. On no return/
SSH: stop hardware work and ask user for physical Fastboot. Never silently mark
restored stock, never interpret process exit0 as radio/native success.

## 2026-10-12 bedtime pause: supersedes ACTIVE entry above

Wi-Fi v3 returned to Fastboot about54s after reboot, with no beacon or SSH.
Read-only LK export logs/pllk-1791753872288099107.* saved. Stock boot_a undo
ACCEPTED without reboot: logs/boot-a-wifi-trial-1791753886161258334.json.
CURRENT LAST PERSISTENT BOOT_A = MATCHING AUGUST STOCK. Last observed Fastboot.
Listener completed600s; no phone trial active. Noob asks to pause for bedtime.
Do not start another hardware trial until resumed.

Detailed next-step handoff: docs/RESUME-NEXT.md. Concrete omitted prerequisite:
reset-ti-syscon.ko before UFS. New hex logger and decoder created/tested in
native ARM64 VM, not yet integrated or verified persistent on phone. Standard
Fastboot fetch unsupported; no partition logging write attempted. Consolidated
hardware result: docs/wifi-v3-first-hardware-result.json. No new phone image
written after the successful stock undo.

## 2026-10-12 resumed: v4 prepared and independently validated

Noob resumed and reported Fastboot. USB001/002 0e8d:201c; fresh ACL/preflight
passed identity, unlocked, slot a and all expected sizes. Stock boot_a remains
last installed pending the next explicit trial receipt.

Audited stock reset supplier: docs/ufs-reset-supplier-audit.json. Three enabled
ti,syscon-reset stock DT nodes; reset-ti-syscon.ko SHA
98c8b506aacb757dc8ef94df2fffe36789c7a64ad2311ffdae263d86d2fe98c8,
matching vermagic/layout/shared imported symbol CRCs. This omitted prerequisite
is now first in seven-module storage list. No MTU3 loaded.

New candidate artifacts/busybox-wifi-ssh-twostage-v4/nord3-busybox-candidate.img
SHA0abe578cdc82a8f42b6bd812f3217dcc622f2a980d93e3c3418bc6dadf731af7,
64MiB; first-stage legacy LZ4 1620973bytes; supplement10195190bytes at24MiB.
Kernel, original loaded-area boundary, metadata/footer and partition geometry
preserved. V3/tools preserved. Fresh session token, separate supervisor,
bootstrap and wifi RAM journals, module begin/OK/failure hex codes/codebook.
No partition log writes; warm-reboot persistence still unverified.

Exact-image guard VM passed: emulated-wifi-v4-image-1791794946333674412/result.json.
Native ARM64 journal/control/reset-module-registration test initially failed
because TEST fixture omitted host-ip and concurrent printk interleaved export;
initial captures retained. Corrected fixture passed all8checks:
emulated-wifi-v4-journals-1791795237342303273/result.json. No handset flash was
performed for those tests. Independent validation docs/wifi-v4-image-validation.json
passed original core supervisor/native DHCP/SSH/calibration/payload receipts,
new logger integration, exact VM, image/source/module/secret/metadata checks and
AVB unlocked/locked policy model. Physical storage/radio not established.

Separate pinned v4 tools: validate_wifi_v4_image.py, test_wifi_v4_image_vm.py,
lynx_boot_a_wifi_v4_trial.py, lynx_wifi_v4_contact.py. Collector self-test passed;
same pinned SSH identity/client key, new image session/init hash. It retrieves
each hex journal individually after authenticated SSH and acknowledgement,
retains raw bytes and decodes checksum/sequence/codebook. Ack timeout now saved
and stops instead of silently dropping the receipt. Host Noobia address remains
192.168.100.106. No new credentials required.

### V4 hardware trial ACTIVE; last installed image now experimental v4

Listener exec78202 ready; receipt logs/wifi-v4-contact-1791796121440275829/result.json.
Authorized trial exec55332; receipt logs/boot-a-wifi-v4-trial-1791796190425679987.json.
boot_a64MiB write and single normal reboot ACCEPTED. LAST PERSISTENT BOOT_A IS
V4 WI-FI DIAGNOSTIC; STOCK UNDO PENDING unless pinned SSH+ack succeeds.
No other partition writes or slot changes. Passive USB/network observation
active. Leave handset/buttons untouched; capture up to600s, then physical
interaction only if needed. Never claim stock restored until new undo receipt.
Pretrial read-only LK: logs/pllk-1791795695626852235.json.

### V4 trial finished; matching stock boot_a restored

V4 returned automatically to Fastboot on USB001/006 ~54.45s after reboot,
without any beacon/SSH. Internal failed stage remains unknown. Fresh ACL,
read-only LK export logs/pllk-1791796477741516715.json, then stock boot_a undo
ACCEPTED without reboot: logs/boot-a-wifi-v4-trial-1791796478398063909.json.
LAST INSTALLED BOOT_A IS STOCK AUGUST again. V4 listener finished600s normally.
Consolidated docs/wifi-v4-first-hardware-result.json. No native journals retrieved.

Offline DT selection lead: current stock LK log explicitly selects dynamic
overlay index5 (project21871, DTS22823). Reconstructed stock vendor-boot DTB
plus stock overlay5 via private libfdt; preserved
artifacts/stock-runtime-dtb-overlay5/stock-merged.dtb and result.json, final
packed416325bytes. No phone DT modifications. Provider graph
docs/ufs-provider-graph-overlay5.json confirms the direct UFS clock, power,
VEMC regulator/reset supplier candidates already in current lists. Original
audit lacked OF aliases for some drivers; compatible literals supplement it.
Offline tree still omits runtime bootloader fixups, so do not call it captured
runtime DT. Reset addition alone did not establish working storage.

### Storage-only outcome diagnostic ACTIVE

Built artifacts/busybox-storage-outcome-v1/nord3-busybox-candidate.img,
SHA85d219fd6625897638ef70ee9abd9959cbf625f0063cecf19905a70f03b5e358,
first-stage1621571bytes. Same stock kernel/reset guards/metadata/footer and
same v4 supplement. It ONLY runs the storage bootstrap, then one delayed
standard bootloader reboot. No radio/SSH startup or new partition log writes.
Code1=base load failed,2=storage load failed,3=no boot_a/no UFS binding,
4=no boot_a/UFS binding,5=payload failed,6=payload verified/extracted,
7=worker deadline180s,8=other. Delays65,90,115,140,165,190,215,240 seconds
from probe start, plus uncertain boot latency. Classifications are timing
inferences, not persistent authenticated hex logs. Tolerance8s; compare with
saved post-return reset fields and physical-interference observations.

All9control fixtures passed (eight results plus invalid clock):
tools/test-artifacts/storage-outcome-control-1791797333352821595/result.json.
Exact-image VM guard passed emulated-storage-outcome-image-1791797624958932543.
Independent layout/core provenance checks docs/storage-outcome-image-validation.json.
Pretrial log logs/pllk-1791797690472335906.json. Trial exec8780, receipt
logs/boot-a-storage-outcome-trial-1791797727376757844.json. Write boot_a and
one normal reboot ACCEPTED. LAST INSTALLED BOOT_A IS STORAGE DIAGNOSTIC;
STOCK UNDO PENDING. Passive observation<=330s. On Fastboot return save LK
and restore stock using tools/lynx_boot_a_storage_outcome_trial.py --restore-stock
without reboot. On no return stop for physical Fastboot. No network listener.

### Storage outcome v1 returned with timing code0x03; stock restored

Storage probe returned to USB001/007 at136.833319994s after reboot, matching
code03 target115s+baseline21.624 within0.209319994s. Inferred outcome: base
and storage insmods completed, but boot_a absent and ufshcd-mtk not bound.
Timing is NOT an authenticated internal log, and user physical non-interference
was requested but not separately explicitly confirmed. Do not mark conclusive.
Post-return LK logs/pllk-1791799014755145548.json show NONRST_REG2=0x28002003,
parsed reset2, watchdog2. Stock boot_a undo ACCEPTED without reboot:
logs/boot-a-storage-outcome-trial-1791799015407889204.json. LAST INSTALLED IMAGE
IS MATCHING STOCK BOOT_A. No active trial/listener.

Concrete next hypothesis: published driver-core.c defaults fw_devlink flags ON
and strict=true; explicit fw_devlink=permissive standard early kernel parameter
retains sync-state ordering without inferred probe gates. Reference saved
docs/wifi-source-reference/driver-core.c; official kernel documentation supports
its semantics. Real kernel binary remains unchanged; published source is not
the exact stock commit. Testing parameter support/behavior on exact stock
kernel is still necessary. No authentication/secure-boot bypass involved.

Builder prepare_fwdevlink_variant.py initially refused the existing nonempty
experimental command line, with no output image created. Actual inherited
arguments are rdinit=/init panic=10 noobia.usb=1. Preserve those and APPEND the
new flag; do not replace them. Prepare storage-only comparison before Wi-Fi.

### Storage-only permissive comparison ACTIVE

New image artifacts/busybox-storage-outcome-v2/nord3-busybox-candidate.img SHA
5f85ae811386ccec50c1eab94649f587621035ca053126788d9627ee666bea25,
first-stage1621570bytes. Original init logic/modules/kernel/supplement unchanged;
fresh token and appended fw_devlink=permissive, preserving rdinit/panic/noobia
arguments. Private permissions and metadata/footer preserved. Exact stock-kernel
VM guard and command line tested: emulated-storage-outcome-permissive-1791803335687320065.
Independent docs/storage-permissive-image-validation.json passed control source,
unchanged provenance and unlocked/locked AVB host model. Pretrial LK
logs/pllk-1791803402511592441.json; offline undo ready.

Trial exec96023, logs/boot-a-storage-permissive-trial-1791803501226694814.json.
boot_a write and single normal reboot ACCEPTED. LAST INSTALLED IMAGE IS V2
STORAGE DIAGNOSTIC; STOCK UNDO PENDING. Observe<=330s, no other commands.
On return capture fresh ACL/LK and restore stock with
tools/lynx_boot_a_storage_permissive_trial.py --restore-stock WITHOUT reboot.
On no return stop and request physical Fastboot. No network listener running.

### Storage permissive comparison returned code0x03; stock undo completed

Comparison returned USB001/008 at136.797089063s after reboot, matching the same
0x03 inference within0.173089063s. The standard fw_devlink=permissive option
did not change this observed result. Actual physical /proc/cmdline has NOT been
read back, so do not claim the parameter was consumed or hypothesis disproved.
Stock driver binary literal ufshcd-mtk verified; reset literal ti-syscon-reset
also verified. Next useful diagnostic must check kernel option delivery,
platform device/driver registration and actual supplier bindings, not repeat
another identical Wi-Fi trial.

Fresh ACL and post-return LK logs/pllk-1791804299363163542.json saved. Stock
boot_a undo receipt logs/boot-a-storage-permissive-trial-1791804300020938688.json.
No other partitions changed. See returned undo command output before assuming
completion; current tool session89055 was polled at this entry.

Stock undo session89055 returned exit0 (send/write OKAY); stock restoration
completed before the following new profile experiment.

### Binding profile v1 ACTIVE

New artifacts/busybox-binding-profile-v1/nord3-busybox-candidate.img,
SHA571fc62e9b6c4ba99ea3bc4c4c327fb147d405fccac073305ffd978fc101c7b0,
first-stage1621959bytes. Same stock kernel/fw_devlink header/v4 supplement and
reset guards. Storage worker followed by ordered READ-ONLY profile. Codes:
1=fw_devlink=permissive absent in /proc/cmdline;2=ufshcd-mtk driver absent;
3=UFS OF/platform device absent;4=first reset supplier not bound;
5=VEMC class name absent;6=waiting_for_supplier1;7=all inspected prerequisites
present/no waiting flag;8=bootstrap failed/timed out before profile. Same
65..240s timed standard return channel. Never call inferred code an authenticated
or persistent kernel log. No hardware-control writes or extra partition writes.

Real ARM64 stock-kernel helper fixtures passed all7codes +lookalike refusal:
emulated-native-binding-profile-1791805258234178270/result.json. All timing/
one-reset fixtures passed tools/test-artifacts/binding-profile-control-1791805258653889446.
Exact-image hardware guard VM passed emulated-binding-profile-image-1791805266481097277.
Independent docs/binding-profile-image-validation.json passed; stock undo ready.
Pretrial log logs/pllk-1791805417943694443.json.

Trial exec73149; logs/boot-a-binding-profile-trial-1791805853343109374.json.
boot_a write and one normal reboot ACCEPTED. LAST INSTALLED BOOT_A IS PROFILE
DIAGNOSTIC; STOCK UNDO PENDING. Passive observation330s; on return fresh ACL/LK,
then tools/lynx_boot_a_binding_profile_trial.py --restore-stock WITHOUT reboot.
On no return stop for physical Fastboot. No network listener. User asked through
async input whether prior two timed returns had buttons/cable untouched; answer
pending. Do not infer their confirmation from silence.

### Binding profile v1 returned code0x07; stock undo issued

Profile returned to USB001/009 at236.912365611s after reboot, matching code07
within0.288365611s. Inference: /proc/cmdline contains fw_devlink=permissive;
ufshcd-mtk registered; actual UFS platform/OF node found; first stock reset
supplier bound; VEMC name found; no waiting_for_supplier1 observed. Attribute
absence also returns7, so don't claim waiting_for_supplier explicitly equals0.
Parameter presence doesn't prove effective ordering if later arguments override
it. No persistent/native log retrieved; physical non-interference question
still pending. Software-return evidence remains conditional timing evidence.

Read-only LK logs/pllk-1791807456604965428.json saved. Stock undo issued:
logs/boot-a-binding-profile-trial-1791807457264766800.json, exec45351 pending
poll. Verify exit0 before marking stock installed. No other partition changes.

Next direct evidence: stock config KPROBES/KRETPROBES/KPROBE_EVENTS/TRACING/
KALLSYMS_ALL enabled, DEBUG_FS_ALLOW_ALL enabled. DYNAMIC_DEBUG disabled, CORE
only, so avoid assuming dynamic-debug control can enable built-in driver logs.
Consider normal kernel tracing of UFS core function return and PM-domain attach
entry/return, retaining raw trace in RAM and reporting classified result via
same bounded timing channel. Verify trace syntax/availability using exact-stock
ARM64 VM before touching handset; no return-value modification or persistent
kernel/bootloader changes. No such tracer is installed yet.

New storage/binding/probe-trace artifact prefixes contain the inherited private
Wi-Fi supplement, so added explicit .gitignore exclusions; existing images
already mode0600 and directories0700. Do not publish those images or secrets.

Stock undo exec45351 returned exit0, send/write OKAY. LAST INSTALLED BOOT_A
IS MATCHING STOCK AUGUST; phone last observed Fastboot001/009. No live hardware
trial or listener. User physical non-interference confirmation still pending.

New observational trace source linux-port/lynx-driver-trace.sh creates only
own trace instance/group; records ufshcd_pltfrm_init retval and PM-domain attach
entry device name/retval. Standard kprobe event API, no retval replacement,
raw-address probe, global trace clear or partition logging. Device.kobj and
kobject.name offsets0 checked against supplied headers; native VM device-add
trace verifies real name fetch. Source retained device.h/kobject.h. Capture
stops own buffer only, avoiding unregistering potentially active return probes.
No tracing candidate has been built or flashed yet.

Native exact-stock-kernel Cortex-A72 trace test PASSED all8checks including
actual getpid return and new RAM loop16 device-name fetch:
emulated-native-driver-trace-cortex-a72-1791808671169674544/result.json.
Full QEMU max feature model produced ZERO guest output and never reached init.
Uninstrumented max baseline also failed before init:
emulated-native-driver-trace-max-1791809280706756030/result.json.
Max pauth=off likewise no init/output; do NOT attribute these to tracing.
New --baseline/init-marker/clean-poweroff/no-exception assertions preserve this
distinction. SVE-disabled virtual feature comparisons started independently;
exec sessions returned by latest tool call. Resolve/test relevant virtual CPU
features before a physical tracing trial. All VM failures/raw outputs retained.

### Native observational trace verified; trace-only hardware trial ACTIVE

Concrete Cortex-A710 and Cortex-A72 exact-stock-kernel tests passed real syscall
PID returns, real signed ENOENT=-2 returns, loop16 device-name fetch, clean
poweroff/no kernel exceptions. Modern max variants all failed before init even
without tracing; concrete model verification resolves the relevant tracer test.
Native collector+BusyBox awk classifier receipt:
emulated-native-driver-trace-cortex-a710-1791811428303994005/result.json.
Classifier semantic18cases passed tools/test-artifacts/driver-trace-classifier-1791811091125715382.

New candidate artifacts/busybox-probe-trace-v1/nord3-busybox-candidate.img SHA
2154dbd63d2de8bab56669db2dabf5f26bb9a8a16774a968717164e8dffccfd4,
first-stage1623202bytes. Stock kernel/header arguments/metadata/footer/supplement
preserved. Own trace instance/group only; never unregister potentially active
return probes at capture. Raw trace/dmesg in RAM0600. No functional return
replacement, raw-address probes or extra partition writes. Codes1=trace setup
unavailable;2=UFS core EPROBE_DEFER;3=matched UFS PM-domain attach negative before
completed UFS core call;4=configuration/lookup errors;5=timeout/IO;6=othernonzero;
7=last UFScore success;8=no usable completion/capture or bootstrap timeout.
Still a coarse timing channel, not persistent authenticated kernel log retrieval.

All10timer/setup/capture/timeout controlcases passed
tools/test-artifacts/probe-trace-control-1791813417611317959/result.json.
Exact-image guard VM passed emulated-probe-trace-image-1791813425392692175.
Independent docs/probe-trace-image-validation.json passed source/layout/native/
semantic/control/provenance/AVB checks. Pretrial LK logs/pllk-1791813788131375860.json.

Trial exec29407; logs/boot-a-probe-trace-trial-1791814948467033764.json.
boot_a write and one normal reboot ACCEPTED. LAST INSTALLED IMAGE IS TRACE
DIAGNOSTIC; STOCK UNDO PENDING. Passive observe330s. On return fresh ACL/LK then
tools/lynx_boot_a_probe_trace_trial.py --restore-stock WITHOUT reboot. On no return
stop for physical Fastboot. No network listener. Do not continue probing if
recovery behaves unexpectedly. User non-interference confirmation remains pending.

### 2026-10-13 resumed: trace outcome inconclusive, stock undo completed

Prior trace trial 1791814948467033764 returned after 261.867293664 seconds;
timed code 0x08, residual 0.243293664 seconds. This combines empty/unclassified
trace, capture failure and worker timeout; do not infer a specific root cause.
Fresh USB node 001/005 required ACL today. Initial preflight timed out without
USB access (receipt 1791899129577653502); no writes attempted by that check.
Read-only bootloader export logs/pllk-1791899213383717164.json succeeded.
Stock restoration logs/boot-a-probe-trace-trial-1791899248771469252.json
completed exit0: boot_a send/write OKAY. LAST INSTALLED BOOT_A IS VERIFIED
STOCK AUGUST IMAGE. No reboot, slot switch, erase or other partition write.

New offline test option test_native_driver_trace.py --load-reset-module loads
the hash-verified stock reset-ti-syscon module after enabling tracing. Exact
stock kernel Cortex-A710 VM passed all16checks, including module insertion,
driver registration, subsequent trace capture/classification and clean poweroff:
artifacts/emulated-native-driver-trace-cortex-a710-module-load-1791899465625435841/result.json.
This verifies that composition for this module in emulation, not physical UFS.
No phone trial/listener active. User physical non-interference confirmation
remains unanswered. No working Wi-Fi/SSH or persistent native log readback yet.

### Direct storage-probe diagnostic prepared and verified offline

Exact stock ufs_mediatek_mod:ufs_mtk_probe symbol verified in stock ELF; audit
docs/ufs-trace-target-audit.json. Published deferred-module trace implementation
retained docs/wifi-source-reference/trace_kprobe.c; published revision is not
the exact stock kernel build. Exact-stock-kernel deferred reset init return
actually captured in Cortex-A710 VM (receipt 1791899787303022097).

Local probe-trace-v2 was NEVER FLASHED. Its native collector passed but timeout
code2 scheduled90seconds, before the180second worker deadline; preserved that
offline candidate and corrected mapping in v3. v3 code1=setup failure,
2=completed MediaTek probe success,3=capture/parser failure,4=expected PID
trace health absent,5=no completed MediaTek probe,6=last probe -517,
7=other probe error,8=worker deadline. Generic UFS/PM events still collected
as raw context. Known PID getpid return is required before interpreting probe
absence/success. RAM trace remains unavailable after reboot; timings indirect.

v3 image SHA b8114a11af588a9f40df0ab125895388a567879a913a973186aacc764b2185b4,
ramdisk1623071bytes. Stock kernel, inherited supplement, metadata/footer kept.
All9timing/control cases passed 1791901374743633330; all12parser semantic cases
passed1791902345247136757. Native collector/module/deferred/errno test passed
all19checks1791901374941857888. Exact-image hardware guard VM passed
1791902748659771646; independent docs/probe-trace-v3-image-validation.json
passed layout, source/test hashes, inherited Wi-Fi provenance and AVB model.
Default Python missing capstone was a host dependency failure only; existing
tools/mtk-venv interpreter ran the exact-image VM successfully.
No v3 phone flash yet. LAST INSTALLED BOOT_A REMAINS STOCK.

### v3 hardware trial ACTIVE; stock undo pending

Trial logs/boot-a-probe-trace-v3-trial-1791902942389926489.json, exec21105.
Fresh identity/layout preflight passed; boot_a diagnostic send/write and one
normal reboot accepted. LAST INSTALLED BOOT_A IS V3 DIAGNOSTIC. Observer armed
before flash, watches USB330seconds. No network listener or additional phone
commands during observation. On return capture fresh USB node ACL and read-only
LK log, then tools/lynx_boot_a_probe_trace_v3_trial.py --restore-stock, no reboot.
If no return, stop for physical Fastboot. No other partitions touched.

### v3 hardware result: code05; stock undo completed

Trial1791902942389926489 returned186.753755745seconds after reboot, timed
code0x05 residual0.129755745seconds: expected PID trace health observed but
no usable completed MediaTek UFS probe result. Could reflect absent/rejected
module instrumentation, probe not reached, incomplete probe, or malformed
trace; do not claim specific cause or direct logs retrieved. Physical
non-interference confirmation still not received. USB001/006 ACL granted.
Read-only LK receipt logs/pllk-1791903796973998037.json, NONRST_REG2=28002003,
raw reset label lk, wdt_status2; same supported-reset pattern as prior tests.
Stock restore logs/boot-a-probe-trace-v3-trial-1791903945089654421.json completed
exit0, boot_a send/write OKAY. LAST INSTALLED BOOT_A IS MATCHING STOCK.
No reboot, slot switch or additional partition changes. No live observer.
Next distinguish module-probe registration rejection from pre-probe deferral,
using stock metadata/source audit before choosing further instrumentation.

### Next collector tested offline; physical confirmation needed

Stock CONFIG_FUNCTION_TRACER is disabled, so the published DYNAMIC_FTRACE
notrace-function rejection branch does not explain this stock build. Stock
UFS module has no mcount table; that absence alone is not a rejection proof.
Other module-probe registration rejection or core deferral remains possible.

Prepared linux-port/lynx-driver-trace-core-v1.sh adds normal builtin supplier
and pinctrl entry/return probes, preserving PM/UFS/module/known-PID events.
Capture saves read-only debugfs devices_deferred and raw trace/dmesg in RAM.
No persistent readback claim or extra partition write. Exact-stock-kernel
Cortex-A710 VM passed all19checks including deferred module init return,
subsequent captures and no exceptions: native receipt1791904584944992946.
This proves definitions/composition in emulation, not physical supplier errors.
No core-collector handset image built/flashed yet.

v3 validator now filters native receipts by matching collector hash instead of
requiring the latest unrelated collector test to match. This preserves strict
tested-source matching while allowing separate offline tests.
LAST INSTALLED BOOT_A REMAINS STOCK, Fastboot USB last node001/006. No observer.
Before treating latest timed code05 as handset diagnostic evidence, obtain
Noob's confirmation whether buttons/cable were untouched during that return.
All tools and raw/failed tests retained under /noobia/lynx.

### 2026-10-13 continued: core checks diagnostic prepared

User asked to continue; this is not an answer to the physical non-interference
question, so prior timing results remain conditional. Prepared core-probe-v1
with normal supplier/pinctrl/PM entry/return traces, exact stock module probe
events, known PID tracing health, kernel module re-registration warning check,
and read-only deferred-device list capture. No return-value changes or binding
override. Complete raw trace/dmesg/deferred data stays in RAM; persistent
retrieval still unverified. Per-kind/per-task stacks distinguish nesting and
interleaving; malformed/unpaired/incomplete captures conservatively unknown.

Core codes:1=trace/setup/capture/correlation unavailable;2=MTK probe success;
3=matching module trace registration warning;4=last UFS supplier check negative;
5=last UFS pinctrl check negative;6=last UFS PM-domain attach negative;
7=healthy tracing without a classified earlier fault (may still have MTK error);
8=worker deadline. Timers unchanged65..240seconds in25second steps; timeout
code8 scheduled after180second worker deadline. One supported software return.

Candidate SHA dbc47af2604563013d2e7591c81b788551938d4467aeedad131370c4ae4eb94f,
ramdisk1623807bytes. Stock kernel/geometry/supplement/metadata/footer retained.
Parser19hostcases passed1791906805649441398. All cases also passed with actual
ARM64 BusyBox under exact stock kernel, including real syscall errno/module
zero return classification: native receipt1791906978626687052. All diagnostics
saved under lynx. Added core-probe artifact prefix to .gitignore (private
supplement inherited); images600/directories700. No phone flash yet.

### Core diagnostic trial ACTIVE; stock undo pending

Independent docs/core-probe-image-validation.json passed. Exact-image guard VM
receipt1791907214700179200 and corrected10control fixtures1791907215051339373
passed. Capture-failure fixture now actually reaches capture after successful
setup, rather than being masked by its expected code1. Stock undo references
and images verified immediately before fresh Fastboot identity/layout checks.

Trial logs/boot-a-core-probe-trial-1791907590015628810.json, exec76440. boot_a
send/write and one normal reboot accepted. LAST INSTALLED BOOT_A IS CORE
DIAGNOSTIC. Passive observer330seconds, no other phone commands while observing.
Noob asked to leave cable/buttons untouched; confirmation still not received.
After return save fresh-node ACL/read-only LK then run
tools/lynx_boot_a_core_probe_trial.py --restore-stock WITHOUT reboot. If no return,
stop for physical Fastboot. No network listener or other partition changes.

### Core trial result07; stock restored

Trial1791907590015628810 returned236.89886006seconds after reboot, code0x07,
residual0.27486006seconds. Healthy tracing, no classified earlier fault: no
module re-registration warning detected, no matched negative last UFS supplier,
pinctrl or PM-domain return classified. Does NOT prove those functions ran for
the UFS device, nor exclude a different failure. Physical non-interference
confirmation pending; result remains timing inference. No native SSH.
Read-only LK logs/pllk-1791907985837575083.json retained; same raw lk reset label
and NONRST_REG2=28002003. Stock undo logs/boot-a-core-probe-trial-1791908116386063554.json
completed exit0, boot_a send/write OKAY, no reboot. LAST INSTALLED BOOT_A STOCK.
No live observer. Next inspect live compatibility, driver override, automatic
probing flag and deferred list using ordinary read-only sysfs/debugfs interfaces.

### Live matching diagnostic built and ARM64 logic tested

Prepared lynx-match-profile.sh and artifacts/busybox-match-profile-v1; SHA
13f82774e2bc6f20e03917c9cf97f8fae100186f91a3477badf1c66c3a36f8c6,
ramdisk1622045bytes. Original stock kernel, loaded-area bound, supplementary
payload and metadata/footer retained. Matching helper does not write binding,
override or automatic-probe settings. Reads live OF compatible NUL list,
driver symlink/override, platform drivers_autoprobe and deferred-device list.
Unknown required interfaces conservatively return1. Extra RAM logs mode600.
Codes1=device/driver/interface unavailable;2=expected driver already bound;
3=unexpected bound driver or override;4=exact stock compatible absent;
5=automatic platform probing disabled;6=live UFS device on deferred list;
7=expected match/override/autoprobe but unbound and not listed deferred;
8=bootstrap failure/deadline. Null/unset override forms handled distinctly
from an override blocking this driver. No forced binding or dependency changes.

Native stock-kernel ARM64 tests passed all13fixture cases plus clean poweroff/
no exceptions, receipt1791908741605825717. All artifacts retained; private
match-profile prefix now excluded from Git. No phone trial yet; STOCK INSTALLED.

### Matching trial ACTIVE; stock undo pending

All10control fixtures1791908848632337411 and exact-image guard VM
1791908847280767755 passed; independent docs/match-profile-image-validation.json
passed. Trial logs/boot-a-match-profile-trial-1791909079698893610.json, exec68434.
Fresh identity/layout passed, boot_a send/write and one normal reboot accepted.
LAST INSTALLED BOOT_A MATCH PROFILE DIAGNOSTIC. Passive USB observer330seconds.
No phone commands during observation. On return fresh ACL/read-only LK then
tools/lynx_boot_a_match_profile_trial.py --restore-stock WITHOUT reboot. If no
return, stop for physical Fastboot. No network listener or other partition writes.

### Matching result07; stock restored; DMA/default-clock audit closed

Trial1791909079698893610 returned236.896536376seconds after reboot, timedcode07,
residual0.272536376seconds: UFS/driver present, expected compatible included,
no blocking driver override, platform autoprobe1; expected driver unbound and
device absent from read-only deferred list. Timing inference remains conditional
on physical non-interference (still unconfirmed). Read-only LK receipt
logs/pllk-1791910295178639083.json has same raw lk and NONRST_REG2=28002003.
Stock restore logs/boot-a-match-profile-trial-1791910336718519438.json completed
exit0/send/writeOKAY, no reboot. LAST INSTALLED BOOT_A MATCHING STOCK.

Retained published platform.c, driver-dd.c, clk-conf.c, scpsys sources; manifest
docs/binding-sources.json. They are reference revision, not exact stock commit.
Platform setup can fail before entering module probe: core DMA configure and
platform of_clk_set_defaults precede PM-domain attach/driver probe. Offline
stock overlay5 UF node has NO iommus or assigned-clock/assigned-clock-parent
properties, docs/ufs-dma-requirements.json. Do NOT infer missing IOMMU module
or load extra drivers based on this closed speculative lead. Bootloader may
change runtime DT; no direct runtime DT dump obtained yet.

tools/lynx_experiment_index.py indexed56trial/restoration receipts without
parse errors; refresh after restore to reflect current stock state. Index
is receipt-derived, not partition readback; confirmations never inferred.
No live observer/network listener. Next inspect platform match/setup return
paths with verified stock-kernel tracing, rather than changing dependency sets.

### Platform collector offline test caught driver-name fetch error

Prepared platform_match, platform_dma_configure and platform_drv_probe entry/
return tracing from verified reference layouts. Buffer4096KiBperCPU (bounded)
and fresh PID health immediately before capture preserve later evidence when
many match calls occur. No handset image/flash of this collector yet.
First platform-v1 VM receipt1791911000693855715 FAILED only driver-name check:
real match calls captured device names and retval0, but driver strings empty.
Standard string fetch requires nested dereference of first-field name pointer:
driver=+0(+0($arg2)):string, matching the already native-tested device-name
fetch. Preserved failed v1 source/raw captures, generated platform-v2 corrected
source and started exact-stock-kernel VM check. Do not attribute this offline
collector error to the phone or reinterpret earlier working core traces.
Stock remains installed; no handset observer or network listener active.

### Noob confirmed physical non-interference; platform v2 collector passed

Noob explicitly answered the question about the last two trials: Lynx returned
on her own; buttons/cable untouched, Noob working at another computer and only
pressing proceed. This validates the non-interference condition for core trial
1791907590015628810 and matching trial1791909079698893610. Their distinct
verified code07 paths plus matching reset evidence provide stronger native
userspace/control-flow evidence. Still no direct native SSH or raw trace readback.
Keep original trial receipts intact; separate confirmation receipt/index link.

Corrected platform-v2 native VM receipt1791911277559522752 PASSED real driver
name ti-syscon-reset, actual kernel returns, stock module/deferred tracing,
all core parser fixtures, fresh PID capture and clean poweroff. Failed v1
source/raw evidence preserved. Exact stock UFS OF match TABLE extracted from
ELF object, docs/stock-ufs-match-table.json, confirming the live-profile string
mediatek,mt8183-ufshci from actual driver data, not a loose compatible literal.

New lynx-classify-platform-trace.awk pairs expected driver matches and UFS
DMA/platform wrapper returns by task/function. All20hostsemantic cases passed
1791911617372937790; native ARM64 parser check started. No platform handset
image built/flashed yet. LAST INSTALLED BOOT_A STOCK; no live phone observer.

### Platform image assembled; exact-image checks pending

Native platform collector+classifier passed all checks receipt1791911695893522215,
including actual driver-name fetch, fresh PID health, real signed kernel
return classification in VM-only paired fixtures and all20semantic cases on
ARM64 BusyBox. Separate Noob confirmation receipt
logs/physical-noninterference-1791911760535070022.json references the two
specific prior trials; index refreshed with confirmation links, original raw
trial receipts unchanged. No confirmations inferred for other historical tests.

Platform-probe-v1 SHA aff51e9e74094d95fa0e2addbf3671326869a07eda2104f09b28821f8b07f56f,
ramdisk1623982bytes. Stock kernel, metadata/footer, geometry and supplement
unchanged. Traces standard platform_match (including exact driver name), DMA
configuration and platform probe wrapper, retaining earlier core/MTK context.
No bind override, module additions or return-value replacement. Fresh PID
health at capture, bounded4096KiBperCPU buffers; no persistent retrieval claim.
Codes1=unavailable/invalid correlation;2=expected-driver match nonpositive;
3=UFS DMA setup nonzero;4=UFS platform probe nonzero;5=no expected-driver match
captured;6=positive expected-driver match, no platform completion;7=platform
probe returned0;8=worker deadline. Code7 is not Wi-Fi success or proof of
final device binding. Private platform-probe image prefix excluded from Git.
No hardware flash yet. Current boot_a remains STOCK.

### Platform trial ACTIVE; stock undo pending

Control fixtures1791913139017836068 and exact-image guard VM1791913208789611740
passed; independent docs/platform-probe-image-validation.json passed. Trial
logs/boot-a-platform-probe-trial-1791913277659661512.json, exec76978. Fresh
identity/layout check passed, boot_a send/write and one normal reboot accepted.
LAST INSTALLED BOOT_A PLATFORM DIAGNOSTIC. Observer330seconds, no phone commands
during observation. On return fresh-node ACL/read-only LK, then
tools/lynx_boot_a_platform_probe_trial.py --restore-stock, WITHOUT reboot.
User says they leave all buttons/cable untouched generally; preserve that
context and separate confirmations for explicit prior two trials. No network
listener, slot change or other partition changes.

### Platform result04: identified nonzero wrapper return; stock restored

Trial1791913277659661512 returned161.977955374seconds after reboot, timed0x04,
residual0.353955374seconds. Classified last matched UFS platform_drv_probe
return nonzero. No earlier last expected-driver nonpositive match or UFS DMA
nonzero return took precedence. This is the first identified failing wrapper,
not yet its exact errno or proof which internal call failed. User generally
confirmed buttons/cable untouched; direct raw kernel trace remains unavailable.
Read-only LK receipt logs/pllk-1791916817493195613.json retained, same raw lk
reset label and NONRST_REG2=28002003. Stock restore
logs/boot-a-platform-probe-trial-1791916836649330931.json completed exit0,
boot_a send/writeOKAY, no reboot. LAST INSTALLED BOOT_A MATCHING STOCK.
No live observer. Next report exact platform wrapper return via bounded timing
encoding, preserving originals and validating the finer timing/decoding first.

Potential guessed-device-name filtering limitation noted: old parsers require
address112b0000 and ufs substring. Current result04 did match a target under
that rule, so do not claim actual alias caused prior absence. Derive the exact
live target name from its OF node symlink in next diagnostic for robustness.

### Exact errno field prepared and tested; stock remains installed

New errno image8856714bafaabc6869ab58fa46194babcd055afd22b88ba93d3d0bf02901afaa,
ramdisk1623859bytes, artifacts/busybox-platform-errno-v1. Stock kernel/geometry/
footer/metadata and supplement unchanged. Resolve live UFS name by exact OF
node symlink (refuse zero/multiple matches), then pair only matching platform
wrapper entry/returns. Live-name aliases tested, but no alias claimed as root.

Timing field0=wrapper0;1..120=negative errno;121=-517;122=larger negative;
123=positive;124=no target/completed return;125=fresh health missing;
126=setup/capture/correlation failure;127=180second worker deadline.
Targetdelay60+2*field seconds; observer380s. New baseline21.9s from explicitly
confirmed core/match trials (21.89886/21.89654 observed offsets). Tolerance0.8s
strictly less than1s midpoint; ambiguous/variable-latency returns unclassified.
This is finer timing inference, not direct kernel log transport or final binding.

All132errno parser cases passed1791917162157499765; all128timers and4failure
cases passed1791917161804628425. Exact-stock-kernel ARM64 BusyBox passed all
cases, actual -2 and0 kernel returns in paired VM-only fixtures, real driver
name fetch, fresh health, live-name empty/alias/duplicate tests:
native receipt1791917283805568899. No physical handset flash yet.

Original USB observer preserved tools/lynx_trial_observer_v1.py before adding
absolute monotonic event/start timestamps to main observer. New decoder
tools/lynx_errno_timing.py uses monotonic reboot-operation/USB difference;
wall timestamps retained to detect wall-clock jumps. All128decoder fields,
4midpoint rejections,60second clock-jump case, missing-monotonic refusal and
observer record fields passed1791917681505981013. No wall-clock fallback.
Final exact-image VM/independent validation pending. LAST INSTALLED BOOT_A STOCK.

### Errno image verified; hardware trial starting

Exact-image guard VM1791917845987575439 passed; independent
docs/platform-errno-image-validation.json passed stock/layout, native parser/
live-name, all-field control and monotonic decoder/observer checks. New
tools/lynx_boot_a_platform_errno_trial.py allows only boot_a, freshly checks
identity/layout and stock restoration images. Observer380seconds and monotonic
decoder0.8second acceptance; original tools/images preserved. Trial exec55181
started with --flash-linux --reboot. Check newest receipt before claiming a
write/reboot completed. If accepted LAST INSTALLED BOOT_A ERRNO DIAGNOSTIC;
stock undo pending until successful --restore-stock receipt. On return fresh
USB ACL/read-only LK, then restore without reboot. If no return, stop for
physical Fastboot. No other partitions/slots or network listener involved.

### Exact field0x6e: platform wrapper ETIMEDOUT; stock restored

Trial logs/boot-a-platform-errno-trial-1791918039172518933.json returned
301.932799034seconds after reboot by MONOTONIC timestamps. Field0x6e (110)
decoded platform wrapper retval-110/ETIMEDOUT, residual0.032799034seconds
within0.8acceptance. Wall/monotonic disagreement about-0.9microseconds, no
clock-jump issue. Fresh PID health and exact live UFS-name correlation required
by this classifier. Still indirect timing transport, not raw kernel trace.
User generally leaves phone untouched. This narrows failure to a timed-out
operation in the storage platform path; it does not identify which call yet.
Do NOT reinterpret as a missing firmware dependency, hardware damage, or proof
that UFS link initialization itself rather than power-domain attach timed out.

Read-only LK receipt logs/pllk-1791918645499566781.json retained. Stock restore
logs/boot-a-platform-errno-trial-1791918656634186671.json completed exit0,
boot_a send/writeOKAY, no reboot. LAST INSTALLED BOOT_A MATCHING STOCK.
No observer/network listener active. Refresh experiment index after this result.

Stock modules.load includes additional nvmem, power/clock and bringup modules
not in our chosen bootstrap set. Investigate actual stock PHY/power-provider
requirements and callback bindings before adding any modules or changing
fw_devlink. No new driver load set or kernel ordering change authorized by
mere speculation; evidence must justify the next controlled boot_a-only trial.

### Timeout-context diagnostic prepared; boot_a trial next

Stock kernel and scpsys message audit passed docs/timeout-message-audit.json.
Host parser68cases, native stock-kernel ARM64 BusyBox parser68cases and VM-only
synthetic /dev/kmsg -> actual dmesg roundtrip passed:
artifacts/emulated-native-timeout-logs-cortex-a710-module-load-1791920834041774615/result.json.
No synthetic kernel messages are injected on the handset. New runtime gates
classification on same-boot exact live UFS platform retval -110 and fresh PID
health; log mask0..63, sentinels124..127, existing60+2*field monotonic carrier.
Power/SRAM/controller/link/UIC/generic timeout bits1/2/4/8/16/32. Error cascades
can set multiple bits; mask0 means no matched retained message, not no timeout.
Control77cases passed1791920908262272481; decoder128cases1791921066672375674.
Local v1 prototype preserved, v2 generalizes health from exactly1 to positive.
No other kernel/module/commandline changes. Candidate b5d0ac87efdf209e849f43c842e0e06e3e4690d0dd3fc0a02f19b4ade7562d98,
artifacts/busybox-timeout-log-v2/nord3-busybox-candidate.img, ramdisk1624419bytes.
Exact-image guard1791921067140614489 and independent validation passed
docs/timeout-log-image-validation.json. tools/lynx_boot_a_timeout_log_trial.py
pins candidate and stock undo, modifies onlyboot_a, observer380seconds.
LAST INSTALLED BOOT_A STILL STOCK until a successful new flash receipt.
User confirms leaves handset untouched and works on another computer. No
physical action currently required. On return obtain fresh ACL, read-only LK,
then --restore-stock without reboot. If no return stop for physical Fastboot.

### Timeout mask32 recorded; stock restored; complementary context prepared

Trial logs/boot-a-timeout-log-trial-1791921141231819557.json returned at
145.874376448seconds monotonic, code0x20/mask32, residual0.025623552seconds.
Same-boot platform-110 gate passed; targeted timeout context matched, none of
the specific mtcmos/SRAM/controller/link/UIC messages matched. This does NOT
rule out these stages or establish the first failing operation. No raw RAM
kernel log retrieved. Read-only LK logs/pllk-1791921372237888900.json has normal
prior reset pattern (NONRST_REG2=0x28002003, wdt_status2). Stock restore
logs/boot-a-timeout-log-trial-1791921382029819893.json exit0/send/writeOKAY,
no reboot. LAST INSTALLED BOOT_A MATCHING STOCK; Fastboot USB001/011 aria rw.

Exact stock error literal inventory docs/stock-storage-error-messages.json
includes MediaTek "probe failed %d", power clk/regulator failures, generic
platform "Initialization failed" and variant init error messages. Published
ufs_mtk_probe emits probe-failed after ufshcd_pltfrm_init error. Compiled literal
is verified but published source is not the exact stock commit. Complementary
bits1/2/4/8/16/32 mean module probe/power-provider/platform-init/variant/regulator/
clock messages. Classifier lynx-classify-timeout-sites.awk, unchanged trace,
gate, modules, kernel, commandline and timer carrier from timeout-log-v2.
Candidate artifacts/busybox-timeout-site-v1/nord3-busybox-candidate.img SHA
21d10aad02191ce95e6c7b8fec70528b57504d56d2f3b8c03654e5826427b832.
Host68parser/native68parser and VM-only real dmesg roundtrip passed; all77control
and128decoder cases passed. Native1791921576945012851, guard1791921576059590941.
Independent docs/timeout-site-image-validation.json passed before next trial.
Next tools/lynx_boot_a_timeout_site_trial.py --flash-linux --reboot, boot_a only,
stock undo pinned. Check actual receipt before claiming installed/completed.

### Complementary mask0; stock restored; five concrete clock suppliers identified

Trial logs/boot-a-timeout-site-trial-1791921643097725725.json returned at
81.832205878seconds monotonic, mask0, residual0.067794122seconds. Same-boot
platform-110 gate passed, none of the six additional message categories matched.
Absence is conditional on message emission/retention and does not prove absence
of callback execution. Read-only LK logs/pllk-1791921807093908628.json normal
reset pattern; stock restore logs/boot-a-timeout-site-trial-1791921824217858469.json
exit0/send/writeOKAY, no reboot. LAST INSTALLED BOOT_A MATCHING STOCK,
Fastboot USB001/012 aria rw. No trial observer or network listener active.
EXPERIMENT-INDEX.json now65receipts, stock accepted installation.

New primary-source finding: __genpd_dev_pm_attach missing provider calls
driver_deferred_probe_check_state, which can return -110 and warn "deferred
probe timeout, ignoring dependency". The exact warning is in stock kernel.
This is a plausible explanation for generic timeout + no lower UFS/scpsys
error messages; actual warning/provider state NOT YET transported from phone.
Do NOT claim literal hardware timeout is proven. Ordinary genpd power-on error
is translated to -517 by the published attach code.

Actual bootstrap includes both mtk-scpsys and mtk-scpsys-mt6983, so loading
these two alone is NOT a fix. init_scp acquires clocks for all declared domains
before provider registration; failure in any domain aborts the provider.
audit_scpsys_clock_suppliers.py resolves all54clock DT specifiers, marks basic/
prefix clocks used by published init, and resolves exact stock named ELF
of_device_id objects (stock_of_match_tables.py). Five required provider modules
are absent from bootstrap: clk-mt6983-cam, -img, -mdp_grp, -mm, -vcodec. First
source-order absent supplier may differ from DT-list order; inspect source init.
Saved docs/scpsys-clock-suppliers.json includes exact table objects. OF aliases
are missing for many modules, so empty alias matches previously hid missing
providers. Compatible literal candidates are explicitly weaker; clk-fmeter
contains topckgen strings but is not the actual top clock driver. Use exact
match tables, not blindly empty alias lists or diagnostic literal matches.

check_power_clock_image_fit.py measured adding exactly these5stockmodules
before mtk-scpsys in base list. All use stockg311738fbb5a8/vermagic, depends
clk-common already loaded earlier. Ramdisk1648126bytes, loaded area21889024bytes
equals existing metadata boundary; fits without moving metadata/supplement.
docs/power-clock-image-fit.json records hashes/metadata. No new image has been
written or flashed; native loading/ABI, final actual compressed geometry and
independent validation still required. A larger final runtime could overflow,
so verify actual build; never assume the fit estimate covers future changes.
Next useful action: prepare a new boot_a diagnostic with exactly5clock suppliers
before scpsys, retaining original errno collector/carrier or proven storage
outcome control; verify stock-kernel ARM64 module loading, geometry and undo.
Prefer one combined checkpoint reporting provider binding + storage discovery,
or errno-first to see whether -110 changes. Wi-Fi second stage is prepared but
cannot launch until UFS reads its verified own-boot supplement. No Wi-Fi/SSH
success yet. Keep existing stock, v4 and all diagnostic images/tools immutable.

### Manual review plus independent tests; Wi-Fi v5 hardware trial next

User explicitly confirms immediate goal Wi-Fi/SSH and requests manual code
review alongside independent tests. No additional agents spawned; review and
separate offline VM processes run concurrently. POWER-CLOCK-REVIEW.md records
findings, caveats and original failed VM fixture. Initial clock-only trace VM
1791922476532408170 lacked AEE prerequisites; unknown symbols recorded. Corrected
isolated native test1791923200142625988 loaded mrdump,aee_aed,clk-common and all5
clock modules successfully, clean poweroff/no exception. These prerequisites
were already in the handset bootstrap. Does NOT prove physical gate/provider
binding. Published init_scp whole-provider dependency confirmed; probes ignoring
registration return mean driver/module presence alone remains insufficient.

New Wi-Fi v5 candidate SHA856e9f39f283593777608fc838afb66a130398732585035dc0c61bfd1925c3af,
artifacts/busybox-wifi-ssh-twostage-v5/nord3-busybox-candidate.img. Exactly5stock
clock modules inserted before mtk-scpsys; base38. Existing Wi-Fi v4 init/runtime,
radio/firmware/private config/supplement/recovery metadata retained; freshsession.
fw_devlink=permissive uses prior-tested argument. Ramdisk1644684bytes, aligned
loaded area4096bytes below original metadata. No extra diagnostic trace/runtime
added; direct native Wi-Fi/SSH trial. Native exact image guard1791923370950111168,
native journal integration1791923373163479790 and independent
docs/wifi-v5-image-validation.json all passed. Collector self-test passed after
adding absolute monotonic event/heartbeat timestamps. Noobia hostIP106 verified.

tools/run_wifi_v5_trial.py prepares900second Noobia UDP collector, verifies
fresh listening receipt BEFORE running pinned tools/lynx_boot_a_wifi_v5_trial.py.
The trial performs fresh Fastboot preflight and boot_a-only flash/reboot,
observes passive USB and pinned native SSH up to600seconds. Listener accepts
only this image's token and Noobia subnet; key-only host-pinned SSH proof gates
fallback cancellation. Captures/journals stay private in logs. No credentials
printed; no unrelated network/device changes. Check actual newest receipt before
claiming installed or completed. LAST INSTALLED BOOT_A STOCK until successful
new write. On failure with Fastboot return fresh ACL/read-only LK then stock
undo using wifi-v5 trial --restore-stock without reboot; if no Fastboot return
stop for required physical interaction. On pinned SSH success preserve Linux
and fetch diagnostics. No bootloader/recovery/slot B write or slot switch.

### Wi-Fi v5 bounded trial completed without contact or Fastboot return; physical step required

logs/boot-a-wifi-v5-trial-1791923548451967966.json: boot_a send/writeOKAY,
rebootOKAY; 600second observation completed with no automatic Fastboot return
and no verified native SSH. Collector logs/wifi-v5-contact-1791923547239542956/
result.json recorded no datagrams. USB recorder
logs/usb-wifi-observer-1791923548613584811.json retained full wall/monotonic
departure/heartbeat/completion, no errors and no subsequent USB enumeration.
Runner logs/wifi-v5-run-1791923546350206862/result.json completed, collector
terminated in its finally block. Collector receipt may still say listening;
it is a preserved partial capture, NOT a live listener now. No live trial or
listener remains. No native RAM journals retrieved; no Wi-Fi/UFS success proven.

LAST INSTALLED BOOT_A Wi-Fi v5 Linux candidate, NOT STOCK. Stock undo pending.
No other partitions/slots touched. Do not claim that missing clocks were the
confirmed hardware cause or that new drivers bound on the handset. Changed
failure timing only shows behavior differs; initialization/stall location unknown.
Unexpected absence of supported fallback: stop hardware experiments until
physical Fastboot is recovered and stock boot_a restored. No further flash,
reboot or auth/BootROM operation is justified while USB is absent.

Next REQUIRED human step: get Lynx back into Fastboot using the previously
successful button sequence and leave USB connected. Ask what is on screen if
that sequence fails; do not select Format data. Once Fastboot USB enumerates,
grant aria rw on the fresh device node and await actual ACL exit0. Fresh
read-only preflight + supported LK log, then immediately restore stock using
tools/lynx_boot_a_wifi_v5_trial.py --restore-stock (no reboot). Pinned stock image
and exact command remain available, accepted prior restores. Stop if identity,
Fastboot, recovery or restoration behaves unexpectedly.

After restoration, use the saved source/VM findings to prepare a smaller
storage/provider diagnostic before attempting Wi-Fi again. Do not repeat the
same v5 Wi-Fi image without a concrete new diagnostic/fix. Five clock modules
loaded in isolated ARM64 VM; hardware provider/gate effects are not emulated.
POWER-CLOCK-REVIEW.md retains ignored-registration-return and generic deferred
timeout caveats. All new test scripts and failed fixtures preserved under Lynx.

### Fastboot physically recovered; Wi-Fi v5 stock undo completed

User "ok go" followed required physical step. USB001/013 enumerated Fastboot;
pkexec ACL completed exit0, fresh preflight identity/slot/layout matched.
Read-only LK logs/pllk-1791924349763626740.json retained306769rawbytes:
rst-from "?", NONRST_REG2=0x20000000, current wdt_status0/exp_type0,
older backup wdt_status5. This differs from prior supported-software-return
pattern (0x28002003/status2), compatible with physical entry but NOT a kernel
crash diagnosis or proof of the stalled stage. Do not treat as confirmed auto
return, since previous600second observation explicitly saw no return.
Stock restore logs/boot-a-wifi-v5-trial-1791924357268970216.json exit0,
send/writeOKAY, no reboot. LAST INSTALLED BOOT_A MATCHING STOCK, Fastboot001/013.
No live observers/listeners. Next prepare progress-before-insmod RAM checkpoints
and a bounded supervisor, initially limiting load set to existing early base
plus five clocks BEFORE scpsys/UFS/radio. This isolates whether the clock
registration itself disrupts our supported reboot path. Do not repeat fullv5.
Review and offline tests may continue; each future hardware image requires
concrete validation and stock undo. Wi-Fi/SSH still unverified.

### Essential path agreed: storage driver checkpoints, then Wi-Fi/SSH

User requests timed one-module-at-a-time storage diagnostics, initcall_debug
and pstore if possible; latest steering keeps scope essential to SSH ASAP.
No further broad debugger work planned. Stock restored receipt above remains
last installed until a successful new trial. New first checkpoint adds only
clk-mt6983-cam after27previously tested base modules; scpsys/UFS/radio excluded.

Preserved module-progress-v1 and v2 prototypes. Debug runtime adds atomic
before/after insertion fields and per-producer LXDG1 stage512 hex records.
Pending fields1..count, completed40+index, failed80+index; field0 means selected
prefix inserted completely, not hardware binding. Fixed90s sample, one normal
reset at120+2*field, observer420s. Never kills an in-flight insmod or reads
hardware control sysfs to determine progress. Hex records remain RAM/kmsg/pmsg
copies; physical persistence/retrieval still unproven.

Stock initcall_debug boot option verified under exact ARM64 stock kernel:
artifacts/emulated-native-initcall-debug-v2-cortex-a710-1791925349086771031/result.json.
Initial test incorrectly used filtered console (loglevel7 hides DEBUG7);
preserved failure. Actual dmesg has module init start/return/timing. Published
TRACEPOINTS configuration registers debug callbacks during boot, so runtime
bool toggling alone is insufficient. Boot option changes startup timing,
therefore count0 known-field calibration must precede decoding count28.

CONFIG_PSTORE/RAM/CONSOLE/PMSG=y. Offline merged DT has no ramoops/pstore node,
but LK physically allocates pstore0x48090000 size0xE0000, console0x40000,
pmsg0x10000; runtime fixups/backend registration unknown. Previous ordinary
BootROM read failed0x1000/no data; no repeat, authentication or bypass.
Saved VM hex decode docs/hex-and-initcall-review.json: bootstrap86, wifi3,
supervisor3 valid records, explicitly NOT handset captures.

Candidates:
count0 artifacts/busybox-module-progress-debug-0-v1/nord3-busybox-candidate.img
SHA465fa84fd647dc04298565db906bcbad3794166d247900bd2246d24702a521d2;
count28 artifacts/busybox-module-progress-debug-28-v1/nord3-busybox-candidate.img
SHA9b5e9ff94c5c441e945ebc3bf714b253d2f8bcfbfcc91182b8d9baf54aeab0e4.
Both retain exact stock kernel, v5 metadata/payload/footer and base module files;
only init/session/progress files/codebook and initcall_debug argument change.
No new partition write until trial. Native control/hex tests passed count0
1791925690834560247 and count28-v2 1791925778589452219. Short5s VM sample
initially captured field68 (camera returned but bookkeeping still in progress);
not a hardware failure. Longer VM10s sample passed, real production remains90s.
Dependency audit docs/module-progress-dependencies.json includes unchanged
vendor ramdisk supplying watchdog/reboot modules: all declared dependencies
present before loads, no shared imported CRC conflict. Exact-image guards
1791925689678224679/count0 and1791925688695057902/count28 passed.
Independent module-progress-debug-0/28-validation.json passed. Timing decoder
128fields/4midpoints/calibration ranges tested1791926226496597850.

Pinned trial tools lynx_boot_a_progress_debug_0_trial.py and _28_trial.py.
Count0 --flash-linux --reboot next; on return fresh ACL, read-only LK and stock
undo via count0 --restore-stock, no reboot. verify_progress_calibration.py binds
known-field0 timing to exact candidate plus matching software-reset record.
Only then count28 trial can run (requires docs/progress-debug-calibration.json).
If any unexpected recovery/no Fastboot return, stop for physical interaction;
do not repeat full Wi-Fi v5 or issue another blind flash.

### Debug timing calibration succeeded; camera checkpoint next

Count0 trial logs/boot-a-progress-debug-0-trial-1791926275369654496.json
returned automatically141.833501310seconds monotonic. Known field0 delay120s
gives baseline21.833501310s, wall/monotonic disagreement-0.151microseconds.
Fresh ACL001/014 completed exit0. Read-only LK
logs/pllk-1791926453078399643.json matches supported software-reset pattern;
verify_progress_calibration.py saved docs/progress-debug-calibration.json.
Interpretation remains conditional on physical non-interference; user leaves
handset untouched during trials. No storage or SSH proof from this calibration.
Stock restore logs/boot-a-progress-debug-0-trial-1791926462807453946.json
send/writeOKAY and exit0, no reboot. LAST INSTALLED BOOT_A STOCK.
Next count28 trial includes exactly first27known base modules plus camera clock;
all other new clocks, scpsys, UFS and radio excluded. Tested diagnostics and
verified baseline already ready, no broader investigations needed first.

### Camera clock insertion checkpoint passed; stock restored; remaining-clock test next

Count28 trial logs/boot-a-progress-debug-28-trial-1791926490441770029.json
returned141.578643856s monotonic, field0, residual0.254857454s against verified
debug baseline. All first27base insertions plus clk-mt6983-cam returned success
before90s sampling. This is NOT individual platform binding/provider proof.
Fresh ACL001/015 exit0, read-only LK logs/pllk-1791926815444532241.json has
rst-from-lk, NONRST_REG2=0x28002003, currentwdt_status2. Stock restore
logs/boot-a-progress-debug-28-trial-1791926821707430952.json send/writeOKAY,
exit0, no reboot. LAST INSTALLED BOOT_A STOCK.

To reach SSH sooner while preserving per-module evidence, next count32 loads
the remaining4clock providers sequentially, atomic before/after checkpoints
for every module. No scpsys/UFS/radio yet. Same kernel/runtime/timing baseline.
Candidate artifacts/busybox-module-progress-debug-32-v1/nord3-busybox-candidate.img
SHA2468d6b65d4f3cd06927db51b9e077708e363a9ecdd112c568203cc4a3eea6dd,
ramdisk1645941bytes. Native ARM64 success/failure/hex receipts passed
1791926887741395669, exact-image guard1791926888214148762.
Independent docs/module-progress-debug-32-validation.json passed.
Next lynx_boot_a_progress_debug_32_trial.py --flash-linux --reboot, boot_a only.
On return fresh ACL/read-only LK then --restore-stock without reboot. On no
return or unexpected recovery stop for physical step. Preserve prior images.

### All five clock insertions passed; stock restored; controller checkpoint ready

Count32 trial logs/boot-a-progress-debug-32-trial-1791927078552586856.json
returned automatically141.596150276s, field0, residual0.237351034s.
All32 sequential insertions completed before sampling; driver binding remains
unproven. LK logs/pllk-1791927439180684178.json matches supported software
reset. Stock undo logs/boot-a-progress-debug-32-trial-1791927449283339667.json
exit0/send/writeOKAY, no reboot. LAST INSTALLED BOOT_A STOCK, USB001/016.

Count34 adds only mtk-scpsys and mtk-scpsys-mt6983 to that prefix, with atomic
per-module checkpoints. No later USB, UFS or radio modules. Candidate SHA
6070a324cbbfc8a1262b94ae111e3a6b3a4cb330e66af54d2363a3e2c5b7edad.
Host control1791927429985198223, native control1791927507179304304 and image
guard1791927507565177462 passed. Independent count34 validation passed.
Next controlled boot_a-only trial; on return read-only LK then stock undo.
Goal remains SSH ASAP: after controller insertion, isolate essential storage
without unrelated USB drivers. No handset Wi-Fi, storage or SSH proof yet.

### Controller insertion passed; stock restored; essential storage candidate built

Count34 hardware trial logs/boot-a-progress-debug-34-trial-1791928031199548761.json
returned141.928076525s, field0, residual0.094575215s. Read-only LK
logs/pllk-1791928371396207838.json matches normal supported software reset.
Both power-controller module insertions completed; binding still unproven.
Stock restore logs/boot-a-progress-debug-34-trial-1791928396853943908.json
send/writeOKAY and exit0, no reboot. LAST INSTALLED BOOT_A STOCK, USB001/017.

Essential-storage count41 candidate SHA
476997a9b518d951f075194004cf288e0214741f571810f8932009b8c585d11e,
ramdisk1646090bytes. Loads first34 modules then seven stock UFS modules,
excluding four unrelated USB drivers and rpmb-mtk. Afterwards bounded partition
discovery plus unchanged read-only own boot payload hash/extraction function.
New nonoverlapping progress fields: pending1..41, inserted43..83, failed85..125;
42=payload pending,84=payload extracted,126=discovery/read failure,
127=unavailable/malformed;0=all modules AND verified payload read complete.
Timing geometry/baseline unchanged. Local control/native/guard tests underway;
candidate is not flash eligible until validation passes. No radio startup yet.

Essential-storage offline results: all module pending/failed states passed
control1791928699335457832; native ARM64 success/module-failure/payload-failure
and three independent hex journals passed1791928698777718833; exact-image
reset failure guard passed1791928715205332570. Dependency audit passed all41
modules with no missing dependencies/shared imported CRC conflict.
Final independent validation additionally checks exact progress interpretation.
Next lynx_boot_a_essential_storage_trial.py --flash-linux --reboot; boot_a only.

### Essential storage did not return in observation window; stock restored

Trial logs/boot-a-essential-storage-trial-1791928863980329500.json accepted
boot_a write/reboot. Completed observer1791928864140505572 captured departure
and no Fastboot return for421.859724s, no capture error. Therefore no timing
field or storage/payload success can be inferred. Host session resumed next
morning with changed USB numbering; current Fastboot appearance cannot be
assigned a return time. No native storage/Wi-Fi/SSH proof.
Current LK1791968894147433004 has rst-from-?, NONRST_REG2=0x20000000, wdt0;
not the supported reset pattern, not a kernel-crash diagnosis by itself.
Stock undo logs/boot-a-essential-storage-trial-1791968968866015972.json
send/writeOKAY, exit0, no reboot. LAST INSTALLED BOOT_A STOCK, USB001/002.

Next narrower candidate: proven34 prefix plus first6 storage prerequisites,
excluding ufs-mediatek-mod, USB/radio startup and payload read. Per-module
pending/returned/failure timing returns to earlier40/80 offset protocol, whose
fields remain nonoverlapping through index40. Preserve failed full41 candidate.

Count40 candidate SHA18a5250d0617c03a305381b6aa24e37a0f2681463e441f7771a586df4a2ec540,
ramdisk1646002bytes. Host control1791969100688105089, native control/hex
1791969173989461527 and exact guard1791969174856388131 passed. Exact40-module
dependency audit passed; independent module-progress-debug-40-validation passed.
Next lynx_boot_a_storage_prefix_trial.py --flash-linux --reboot, boot_a only.
Normal reboot is not an independent hardware failsafe: published device_shutdown
calls wait_for_device_probe, so a stuck probe can block the normal reset syscall.
This is a source-based possible explanation, not a retrieved handset diagnosis.

### Six storage prerequisites inserted; stock restored; guarded UFS probe next

Count40 trial logs/boot-a-storage-prefix-trial-1791969301603078904.json returned
141.729712147s, field0, residual0.103789163s. First40 insertions completed by90s.
LK1791969570087577342 has normal supported reset: lk, NONRST28002003, wdt2.
Stock undo logs/boot-a-storage-prefix-trial-1791969590915731899.json accepted
send/write, exit0, no reboot. LAST INSTALLED BOOT_A STOCK, USB001/006.
Full41 failure is now narrowed to main UFS insertion or subsequent payload read;
not yet proof which one. Published normal reboot waits on active probes, so
software supervisor existence does not guarantee a successful ordinary reset.

Exact stock CONFIG_MAGIC_SYSRQ=y. Source audit docs/sysrq-reset-path.json and
real stock kernel ARM64 VM emergency reset1791969728780655793 passed. Two
incorrect source-header assumptions were corrected; failed audit assertion
receipt preserved. Native VM demonstrates reset interface, NOT handset Fastboot
destination. Ordinary reboot-mode notifier is expected to prepare bootloader
mode before device_shutdown; subsequent emergency reset skips shutdown/probe
wait. This destination remains conditional until hardware observation.

Prepared main-UFS-only candidate artifacts/busybox-ufs-probe-emergency-v1,
SHAf65ec3de06c76a85f7796492476c5eba89666aa79bf59c6c15a0037f615e7b60,
ramdisk1646147bytes. Exactly41 sequential insertions, no payload read/radio.
At encoded deadline request normal bootloader reset once in background, then
if still running after5seconds, one supported SysRq emergency reset. No raw
register, calibration, authentication or additional partition modifications.
Runtime checks reset interface writable before loading modules. Existing
watchdog/reboot-mode guard retained. Normal and emergency timing grids are
decoded only when interpretation is unique; ambiguous results rejected.
Host control1791970009488482376 and probe-safe timing tests passed. Native
control/hex and exact-image guard running after user interruption/resume.
No UFS/fallback hardware flash yet; latest stock state confirmed by receipt.

UFS/fallback native control/hex1791970247505771668 and exact guard
1791970248209622937 passed; independent ufs-probe-emergency-validation passed.
Host/reset paths are fixtures in control tests; real SysRq only exercised in
isolated VM so far. Next lynx_boot_a_ufs_probe_trial.py --flash-linux --reboot.
Normal request can prepare bootloader intent but emergency destination is not
assumed proven. On any unexpected recovery/no return stop for physical step.

### UFS/fallback trial did not return; physical Fastboot needed

Trial logs/boot-a-ufs-probe-trial-1791970441950636428.json accepted boot_a
write/reboot, completed observation with fastboot_return_observed=false and
native_ssh_verified=false. At2026-10-14 09:41:03UTC lsusb has no Lynx node.
LATEST INSTALLED BOOT_A: UFS/fallback diagnostic f65ec3de..., NOT STOCK.
No stock undo issued because no Fastboot connection. No live trial/listener.
Do not run another hardware experiment until Lynx is physically returned to
Fastboot, fresh node ACL/preflight, read-only LK and verified stock undo.
Exact undo: lynx_boot_a_ufs_probe_trial.py --restore-stock (no reboot).

This negative trial does NOT prove emergency reset executed, main UFS entered,
or kernel globally froze. The runtime tests -w /proc/sysrq-trigger before its
clock/worker; an unavailable/denied interface returns into stop without an
ordinary reset. Actual handset interface availability was not independently
calibrated; VM success does not resolve that alternative. Other possibilities
include blocked logging/probe/reset or reset to a non-Fastboot destination.
Do not classify exact stop location from this missing return.

Next offline correction: preflight interface-check failure must request the
already-proven ordinary reset instead of merely stop. Before further UFS load,
use an ordinary-reset-only presence checkpoint with the passing40 prefix (or
bare calibrated prefix) to establish whether handset SysRq is actually writable.
Preserve current frozen image, failures and all raw captures; no authentication,
raw register, slot B or other partition changes. Primary goal stays SSH ASAP.

### Fastboot recovered; UFS/fallback stock undo completed; harmless interface test ready

User said ok go; USB001/007 Fastboot visible. ACL completed exit0. Fresh LK
logs/pllk-1791975178541994109.json has rst-from-?, NONRST20000000, wdt0x800;
not the supported normal software-reset pattern. Do not infer emergency executed.
Stock restore logs/boot-a-ufs-probe-trial-1791975202358594351.json send/writeOKAY,
exit0, no reboot. LAST INSTALLED BOOT_A STOCK, USB001/007.

Prepared artifacts/busybox-reset-interface-v1, candidate SHA
ea2715f2f7ec48f56fcdc42d1a380b8aeba030db5903d0a6b89acaee11f107ce,
ramdisk1645677bytes. Bare calibrated prefix (no additional module insertion),
one harmless SysRq help request in a supervised worker, ordinary reset only.
Field0=help write accepted (not an emergency reset),1=rejected,2=interface
missing,3=help write pending at90s. Delay120+2field, same verified baseline.
Host fixtures1791976957631614284 passed all4 cases. Native stock kernel/ARM64
1791977208421522979 passed real help handler, simulated missing interface,
hex journals, two fake ordinary resets and clean poweroff. Exact image guard
1791977207955943685 passed. Final validation/timing check before hardware trial.

### Handset SysRq help accepted; ordinary reset succeeded; stock restored

Trial logs/boot-a-reset-interface-trial-1791977398018947610.json returned
141.712182378s, field0, residual0.121318932s: harmless help write accepted.
Fresh ACL001/008 exit0. LK1791977730641379113 matches supported normal reset
(lk/NONRST28002003/wdt2). This supports actual handset interface availability;
does not prove emergency Fastboot destination or execution during failed UFS.
Stock undo logs/boot-a-reset-interface-trial-1791977852891092432.json send/write
OKAY, exit0, no reboot. LAST INSTALLED BOOT_A STOCK, USB001/008.

Next essential source review: distinguish inserted power-controller module
from bound controller and registered ufs0 domain object, without main UFS load.
Saved source shows UFS init enables PHY/clocks and calls secure firmware; a
main-UFS failure need not be a userspace or module-list error. Candidate boot
commandline already has panic=10; panic/reboot is another possible cause of
lost software-supervisor return. Neither kernel panic nor firmware mismatch
is established by current captures. No further blind UFS flash.

Prepared read-only metadata snapshot artifacts/busybox-power-metadata-snapshot-v1,
SHAd68afb3526a28a81c41a0b1b85a4816f85269fddb80c5eac11caadc5402ab598,
ramdisk1646094bytes. Proven34 prefix only, then driver symlink and directory
queries; no main UFS/PHY/storage/calibration/radio load or emergency reset.
Result bitmask:1=controller1c001000 bound to mtk-scpsys-mt6983,
2=debugfs ufs0 domain object present,4=debugfs mounted,8=SysRq access writable.
Domain presence requires debugfs bit; impossible combinations are reserved.
16=base insertion failed,17=base pending,18=query pending;125/127 malformed/missing.
One normal reset at120+2field seconds, fixed90s snapshot, existing debug baseline.
No register/control-file read; genpd presence does not prove power-on/onecell
provider success. Published source adds runtime debugfs domain directories;
exact stock module rodata contains both expected names. Audit passed.
Host actual-query fixtures1791979532934515330 passed8cases, native ARM64
1791979748928539801 passed mask15/mock-positive, base-failure16 and real VM
query12 (debugfs and SysRq, no MediaTek domains), valid hex and clean poweroff.
Exact image guard1791979748440362566 passed. Final timing/validation before trial.

### Snapshot returned near base-failure code; no metadata flags established

Trial logs/boot-a-power-snapshot-trial-1791980226181199915.json returned
173.359010364s. Old2s-grid decoder nearest16/base-load-failed, residual0.47449s.
No power_metadata_flags emitted. Snapshot full mask15 would have expected
171.8335s; a1.5255s profile/boot/shutdown offset is an alternative to actual
base failure. No exact failed module/log readback. Treat result provisional;
do not assert domain absence or base failure as established hardware fact.
LK1791981323760922154 matches normal supported reset. Stock undo
logs/boot-a-power-snapshot-trial-1791981596680295648.json send/writeOKAY,
exit0/no reboot. LAST INSTALLED BOOT_A STOCK, USB001/009.

Next snapshot v2 uses5s slots/tolerance2s (separation remains unambiguous),
adds exact failed module field32+index, and persistent log file interface
presence as mask16 (metadata only, no record contents read). Masks0..31;
32=base pending,33..66=failed module1..34,67=query pending,68/69 malformed/missing.
Same proven34 prefix and normal reset; no main UFS/emergency/storage/radio.
Wider observation540s covers the largest error field. Preserve v1 as raw evidence.

Snapshot v2 candidate artifacts/busybox-power-metadata-snapshot-v2 SHA
a19be93f2ae73debfb51dfd02e582ba97b31d882491ea10f2a05790db4efa9df,
ramdisk1646179bytes. Extra flag16=persistent log file interface (pstore regular
file or /proc/last_kmsg) exists; NOT content/readability or retained crash proof.
Host control1791982245571194358, native ARM64/control/hex1791982519088374458
and exact guard1791982519477207719 passed. Wider timing test validates offsets
including1.5255s and rejects invalid/midpoint signals. Existing debug baseline
with explicit assumed maximum2s profile/startup variation; larger drift remains
unclassified or potentially unsafe to interpret and requires scrutiny.
All masks0..31, exact failure33..66, base pending32, query67, malformed68/missing69.
Next lynx_boot_a_power_snapshot_v2_trial.py --flash-linux --reboot after final
validation. On return fresh ACL/read-only LK/stock undo, no reboot. Main UFS,
radio, raw registers, calibration, slot B and recovery foundations unchanged.

### Wide snapshot mask31 returned; controller/domain/log interfaces present; stock restored

Trial logs/boot-a-power-snapshot-v2-trial-1791983380958537683.json returned
296.908668609s, mask31, residual0.075167299s. Timed flags alltrue: controller
bound, ufs0 domain object present, debugfs mounted, SysRq access writable, and
persistent log file interface exists (pstore regular file OR /proc/last_kmsg).
This does not establish actual retained data, onecell lookup or domain power-on.
Supported LK reset logs/pllk-1791984261094223261.json matches lk/NONRST28002003/wdt2.
Stock undo logs/boot-a-power-snapshot-v2-trial-1791984360598234019.json accepted
send/write, exit0, no reboot. LAST INSTALLED BOOT_A STOCK, USB001/010.
No active observer. Wider frame resolves current startup/module ambiguity;
do not retroactively assume v1 was definitely mask15 versus a transient failure.

Next essential diagnostic: bounded read of already exposed kernel log files,
without main UFS. Prefer validated LXDG1 records with the frozen UFS session
token; report persistent-content/stage/exception clues through safe normal-reset
timing, not an invented direct log download. Interface existence alone is not
readability or evidence of the UFS failure. Preserve originals and private logs.

Prepared bounded retained-log query artifacts/busybox-retained-log-query-v1,
SHA3f713d6949c9e5c6fcab86e76b8b22e7c949bc45f0b140fa6ac74c6d85287412,
ramdisk1646979bytes. Same34 prefix, no main UFS/radio/block/raw RAM access.
Reads only regular non-symlink files from mounted pstore and /proc/last_kmsg,
max8files/1MiB each into private RAM. Reference is frozen UFS/fallback session
from f65ec3de... image. Select one bounded record: prefer checksum-valid
reference, then raw reference, then generic; never OR markers across files.
Flags1=data,2=reference token text,4=valid capsule checksum,8=panic/oops,
16=CFI failure,32=UFS/power/clock/SMC symbol within60lines of CallTrace.
Markers in one selected record may still refer to different incidents; token
and SHA are not authentication or complete sequence verification. No markers
does not establish absence of crash; old UFS logs may no longer be retained.
64=base pending,65=query pending,66=base failure,68/69 malformed/missing;
5s slots/tolerance2s, observation540s, one ordinary reset, stock undo ready.

Host corpus1791985908553974847 passed12cases incl checksum failures, frame
selection/no cross-file mixing,8-file/1MiB bounds and pending/failure resets.
Native ARM64 parser1791986209443342211 passed synthetic matching crash63,
base-failure66 and empty-query0, checksummed own journals/clean poweroff.
Exact guard1791986209756872172 passed. Timing test corrected a fixture that
mistakenly labelled valid field7 as reserved; no runtime/image change.
Independent validator corrected a token variable shadowing image-reference
bytes; no runtime/image change. Final validation before hardware query.

### Retained query found data and a checksum-valid failed-UFS session record

Trial logs/boot-a-retained-log-trial-1791987156215800161.json returned
178.390434683s, selected-record mask7, residual1.556933373s (inside widened2s
tolerance). Nonempty bounded data, exact F65-session token, and at least one
SHA256-valid stage capsule found. Selected record has no detected panic/oops,
CFI failure or UFS/power CallTrace marker; this is NOT a global no-crash claim.
No full raw handset file was downloaded; data interpretation is through the
normal-reset timing signal. Capsule checksum is integrity, not authenticated
identity or sequence completeness. Supported LK1791988064142846318 has
lk/NONRST28002003/wdt2. Stock undo1791988094405919062 accepted send/writeOKAY,
exit0/no reboot. LAST INSTALLED BOOT_A STOCK, USB001/011. No active observer.

Next read-only query extracts the last checksum-valid stage512/status in a
selected retained reference record. Prioritize common results41(before main
UFS),83(insertion returned),125(insertion failure),0(all prefix completed) in
transport slots1..4; map all other valid reference statuses too. A retained
marker brackets execution/logging; it is not an exact instruction stop or
guaranteed most recent boot across files. No new UFS activation needed.

Prepared artifacts/busybox-retained-stage-query-v1 SHA
1dc206e7ba79067711957f9d8b40ea19d53594b38a4d7e51026275035262bc52,
ramdisk1647983bytes. Source still bounded8files/1MiB, one standard reset,
proven34 prefix. Prefer a record with a verified stage512 progress capsule;
use last such valid capsule in its sampled byte order, not maximal sequence.
Map125valid reference statuses, prioritizing41/83/125/0 as transport1/2/3/4;
0=no reference progress marker,126=base pending,127=query pending,
128=base fail,129=bad reference/map,130=missing worker.5s slots/tolerance2s,
observation900s covers largest rare code; common UFS outcomes return quickly.
Host corpus1791990215206140603 passed18cases incl newest valid marker,
completion/failure status, invalid-last rejection, non-progress stages,
selection/checksums and read limits. Native ARM64 stock-kernel
1791990450364509089 and exact guard1791990450691998540 passed. Timing corpus
passed all valid codes/offsets and midpoint rejection. Independent validation
passed. Next lynx_boot_a_retained_stage_trial.py --flash-linux --reboot; on
return fresh ACL/read-only LK then verified --restore-stock without reboot.

### Retained UFS marker41 observed; stock boot_a restored

Retained-stage trial logs/boot-a-retained-stage-trial-1791990934592699635.json
returned146.88020619099916s, transport1/status41, residual0.046704881s.
Last checksum-valid stage512 in the selected bounded F65 reference record is
the marker immediately before ufs-mediatek-mod.ko insertion. This brackets
the load/probe/logging boundary; not an exact instruction stop, guaranteed
newest boot across files, or complete sequence proof. No raw retained file
downloaded. LK1791991595248441968 has lk/NONRST28002003/wdt2.
Stock undo logs/boot-a-retained-stage-trial-1791992392183165910.json accepted
send/write OKAY, exit0, no reboot. LAST INSTALLED BOOT_A STOCK, USB001/012.

Prepared offline artifacts/busybox-ufs-registration-only-v1 SHA
034177798aed0cb0210e51eaf563eefc055abe6fcdbde3d272f89003b1880a56,
ramdisk1646403. Proven first40 prefix followed by original main UFS module,
SHA31e452411297a57a6ed4c31b207c3b4604fa8b55acd95cff6135c680846614a4.
RAM-only driver_override guard requires exactly one unbound platform target,
exact compatible mediatek,mt8183-ufshci, exact runtime OF node
/sys/firmware/devicetree/base/ufshci@112b0000, empty/(null) writable override;
validates all targets before writing, no unbind/existing override overwrite.
Exact stock OF table audit and merged overlay5 DT agree. Module unchanged.
One normal reset only, 90s sample, six5s slots120..145/tolerance2s/240s observer.
0=guard verified+insertion returned,1=guard refused,2=main insertion failed,
3=pending,4=prefix failure,5=missing/malformed. No UFS hardware probe, storage
payload/calibration read, raw-register writes or radio startup requested.

Native fixture1791993179707640864 failed only outcome expectations because
the shortened1s sample preceded completion of forty fake loads. All8 guard
cases/hex/reset-count/poweroff passed. Test-only sample extended10s/deadline12s,
pending fake load20s; candidate/runtime unchanged. Rerun in progress.
Exact image guard1791993307256277019 passed, correctly refuses loads/reset
without MTK reset devices. Independent validation and native rerun pending;
do not flash until they pass. All prior images and recovery foundation retained.

### Guarded UFS module registered on Lynx; stock undo completed

Native guard/supervisor1791993306392303788 passed all8 guard cases,5 outcome
cases, capsule checksums/sequences, reset count and clean poweroff. Exact-image
guard1791993307256277019 passed. Independent ufs-registration-validation.json
passed unchanged stock kernel/module/metadata/payload, prefix provenance,
declared dependencies/import CRCs, source/native receipts and AVB policy model.
Timing test passed25cases. Source/tool/test artifacts retained under Lynx.

Hardware trial logs/boot-a-ufs-registration-trial-1791993758249868766.json
returned141.85409067699948s, field0, residual0.020589366999s. Conditional on
non-interference and supported-reset pattern, guard verified and original UFS
module insertion returned with hardware matching blocked. Main module init
and registration can complete; the unguarded failure is associated with the
matching/attachment/probing path, not proven exact function or root cause.
No physical UFS storage read, Wi-Fi or SSH established. LK1791994813904320388
has lk/NONRST28002003/wdt2. Stock undo1791994932301896630 accepted send/write
OKAY exit0, no reboot. LAST INSTALLED BOOT_A STOCK, Fastboot USB001/013.

New offline logging route: exact stock kernel VM1791994814225571079 proves
tp_printk boot argument sends a selected dynamic syscall trace event into
dmesg; no exception, clean poweroff. Published primary trace source saved by
audit_trace_printk_path.py at commit81ec42ad..., not exact stock commit.
This does NOT prove UFS function instrumentation, physical event execution,
or phone pstore persistence. Next native test loads the exact UFS dependency
closure on QEMU with no MTK matching devices, registering six selected
function-entry probes. Only after that, prepare a narrow persistent trace
hardware experiment. Prior broad tracing images remain unchanged.

### Exact stock module trace setup verified; controlled traced probe prepared

Native stock UFS dependency closure loads/driver registration succeed on
QEMU. First module trace test1791995233130052719 created all6 events but
literal printf enable writes returned1. Do not equate those statuses with
proof that events remained disabled: no activation readbacks were collected.
Bounded two-byte dd writes passed1791995376825967320. Actual setup script
with dd and explicit enabled=1 readbacks passed1791995743905771054 for six
module functions plus platform_drv_probe/dev_pm_domain_attach/genpd_dev_pm_attach.
No exception, clean poweroff. Some initial source function targets were
inlined or in the builtin kernel; exact module symbols corrected before use.

Prepared artifacts/busybox-ufs-trace-probe-v1 SHA
30a2757ef742a859a24d577b35bf33111c3ed3cc5d43baa4199cf0d889f363ff,
ramdisk1647445, sessiona886c9c0269ceb1c38536059332860de.
Exact first40 prefix, RAM-only matching guard, original UFS insertion,
then9 selected dynamic entry events enabled/read back and tp_printk output.
Event names lx<TOKEN>_<index> identify this image's records. After ready,
verify original override still set/unbound, clear it, verify cleared, request
only exact guarded platform device via one bounded drivers_probe write.
No unbind/partition storage writes/calibration read/radio/payload startup.
Core event records lack device-name arguments and could represent other
devices; do not attribute them to UFS without contextual evidence. Module
function entries are more specific. No recorded entry is proof of return.

Capsule stage515/status16=trace ready,17=before probe request,18=probe returned.
Outcome0=probe returned+expecteddriverbound, not block access proof;
1guardrefused/2modulefail/3pending/4prefixfail/5missing-malformed,
6tracesetupfail(no probe requested)/7probewritefail/8notbound/9clear/prereqrefused.
One standard reset only,90s sample,5s slots120..165/tolerance2/240s observation.
Actual normal shutdown may stall waiting for a probe; on no return stop for
physical Fastboot, then save LK/stock undo without reboot. No emergency reset
or authentication bypass included. Stock undo command already verified.

Probe safety/refusal fixtures1791996752774450077 passed8cases and exact-device
request counts. Supervisor1791996753599877089 passed9outcomes/single reset.
Timing corpus passed41cases. Exact image guard1791996798959207899 passed.
Final independent validation in progress. LAST INSTALLED BOOT_A STILL STOCK.

### Traced UFS probe did not return; physical Fastboot needed

Final independent ufs-trace-probe-validation.json PASSED. Authorized trial
logs/boot-a-ufs-trace-probe-trial-1791997650231626827.json accepted boot_a
send/write and one normal reboot, but no Fastboot return within240seconds;
native_ssh_verified=false. USB observer receipt saved by trial tool.
LAST INSTALLED BOOT_A IS TRACED UFS PROBE image30a2757e..., NOT STOCK.
Stock undo PENDING. Stop hardware commands until physical Fastboot recovery.
Do not infer exact hang, trace activation on handset, event execution, or
pstore persistence from non-return. Parent reset can block behind probing.

On user Fastboot recovery: inspect actual USB node, await ACL exit0, collect
supported read-only LK log, then
python3 /noobia/lynx/tools/lynx_boot_a_ufs_trace_probe_trial.py --restore-stock
Verify send/writeOKAY and exit0; NO reboot/slot switch/erase/other flash.
If recovery state is unexpected, stop. Only then run a validated read-only
retained log query of this unique traced-image token, without new main UFS.

While passive observation was active, prepared read-only query source
linux-port/lynx-retained-ufs-trace-runtime.sh using
tools/prepare_retained_ufs_trace_query.py. It selects one bounded regular
non-symlink record(max8files/1MiB), checksum-valid reference capsules,
last token-specific lx<TOKEN>_[1-9] trace entry or stage515 phase16/17/18.
No cross-file mixing or full-sequence/authentication claim. Generic core
events can refer to other devices. Entry is not return proof. Prefix34 only.
This runtime is NOT YET TESTED, PACKED, VALIDATED OR FLASHED. Do not use until
host/native/bounds/geometry/guard checks pass. Source generator corrected
initialization replacement anchors before generating; saved all artifacts.
No active observer remains. Next required action is Noob's physical Fastboot.

### Physical Fastboot recovered; traced-probe stock undo completed

User resumed with ok go; actual USB001/014 Fastboot observed and ACL completed.
Supported read-only LK logs/pllk-1791998271005283290.json saved (raw306769bytes).
Current reset label?, NONRST_REG2=20000000/wdt0 differs from normal timed return;
do not treat it as proof of a particular crash or reset cause. Stock undo
logs/boot-a-ufs-trace-probe-trial-1791998307093549444.json accepted send/write
OKAY exit0/no reboot. LAST INSTALLED BOOT_A STOCK. Slot B/foundation unchanged.

Prepared artifacts/busybox-retained-ufs-trace-query-v1 SHA
299c1ab3207e48d546077506690a1cfb91bdf05d0fe2c63d3a56dc4feff5ef75,
ramdisk1647362. Proven34 prefix, unchanged stock kernel/recovery metadata and
supplemental payload. Reads max8regular non-symlink retained files/1MiB each.
Reference token is traced-probe imagea886c9c0269ceb1c38536059332860de.
Only checksum-valid reference capsules allow trace/phase interpretation;
one selected record, prefer valid token-specific trace over phase-only.
Last event in sampled byteorder1..9; generic7..9 may be other devices.
10trace-ready phase16/11beforeprobe phase17/12probereturned phase18 but no
matched trace entry retained;13validcapsule no recognizedphase/entry;
0no validatedref;14basepending/15querypending/16basefail/17bad/18missing.
Five-second slots120..210, tolerance2s, observer270s, one normal reset only.
No new mainUFS/PHY/storage/radio startup or raw-memory reads. Checksums not
authentication/complete sequence proof; entry not return proof; retained
byteorder not newest boot or last CPU instruction. Full raw log not downloaded.

Host corpus1791998563543802348 passed30cases including all9events, wrong token,
invalid checksum, phase selection, last entry, no cross-file mixing,8file/1MiB
bounds and pending/failure resets. Exact image guard1791998644340087043 passed.
Timing corpus passed77cases. Native ARM64 parser test in progress; final
independent geometry/source/provenance/boot-policy validation pending.
Do not flash until native and independent validation pass. No phone trial active.

Native ARM64 query1791998643455841065 PASSED: synthetic matching trace4,
basefailure16, emptyquery0, three fake reset calls, complete own diagnostic
checksums/sequences, clean poweroff/no exception. Final independent retained
ufs trace validation PASSED. Trial harness validator argument corrected to
--count34 before hardware use; image/runtime unchanged.

Read-only query trial logs/boot-a-retained-ufs-trace-trial-1791998823833905362.json
accepted boot_a write and one reboot; passive USB observer270s running.
LAST INSTALLED BOOT_A QUERY image299c1ab3..., STOCK UNDO PENDING.
On return fresh USB ACL/read-only LK, then
python3 /noobia/lynx/tools/lynx_boot_a_retained_ufs_trace_trial.py --restore-stock
Await send/writeOKAY exit0, no reboot. If no return stop for physical Fastboot.
No mainUFS or radio activation in this query. No parallel hardware trial.

### Retained handset trace found reference-clock entry; stock undo completed

Query1791998823833905362 returned166.8020574029979s, field5,
residual0.031443907003s. Selected bounded record has checksum-valid traced
reference capsule and its last token-specific entry is ufs_mtk_setup_ref_clk.
This establishes a retained module-function entry (conditional on supported
reset/non-interference), not a completed function, exact stop or full raw log
retrieval. Later uninstrumented work may have executed. Generic core event
attribution is not involved in field5. LK1791999113646276335 matches
lk/NONRST28002003/wdt2. Stock undo1791999205104712325 accepted send/write
OKAY exit0/no reboot. LAST INSTALLED BOOT_A STOCK, Fastboot USB001/015.

Exact stock binary audit saved docs/stock-ufs-refclk-audit.json and disassembly.
576byte ufs_mtk_setup_ref_clk body: on-path call __arm_smccc_smc at+0x88,
after call+0x8c, request-store+0xa0, afterstore+0xa4, acknowledgement-read+0xf0,
afterread+0xf4. Firmwarecall args0xc2000276/8/1. Bounded poll deadline adds
3000000nanoseconds; absent ACK alone should return a timeout, not prove a hang.
Source matches broad path, but exact compiled offsets verified independently.
Possible next boundaries include firmware call, MMIO access, function return,
or later untraced crypto work. Do not bypass firmware/ACK checks or force clocks.

Preparing a standard kprobe/kretprobe trace variant at those audited offsets,
plus function return and crypto entry. Must pass exact native activation and
image/guard/control checks before another hardware trial. No raw address writes
or modified stock .ko files; instrumentation is ordinary kernel RAM tracing.

### Finer reference-clock diagnostic verified offline; v1 rejected and retained

Reference-clock v1 imageeca2aec00366ccb05721aa3bbb7f6bdb190eeaa0f4c496d61b097fc98c4b223f
was NEVER FLASHED. Native1791999757702499570 accepted first6 markers but
rejected+0xf4(after-read NOP), so setup stopped and later probes were not
attempted. No exception/clean poweroff. Rejection alone does not establish
its cause. Preserve v1 image/source/failed receipt; do not use it on Lynx.

Corrected v2 uses audited+0xf8(after-read barrier) instead. Native
1791999942177265100 passed all9 activation/readback checks, exact stock module
dependency loading/driver registration, no exception and clean poweroff.
Probe-safety fixtures1791999988212858373 passed8cases. Parent probe/reset logic
unchanged. v2 setup SHA51fef6ebbb32c9262b24c7b97597c2dff995c031ff87ca24d035fc2cef1b2824.
Standard kprobes/kretprobe only, no module binary/firmware logic changes.

Prepared artifacts/busybox-refclk-trace-probe-v2 SHA
b4a505426c91b3a0c151b977ddcfbfddeabcca612a59959408230c19d317aea1,
ramdisk1647522, session69adf9d14707d848063b861b8f248748.
Markers1refclkentry(on arg),2before on-pathSMC+88,3afterSMC+8c,
4before requeststore+a0,5afterstore+a4,6before ACKread+f0,7afterread+f8,
8refclkreturn(signedretval),9cryptoentry. All are UFS-specific; old query
codebook assumption7..9genericcore MUST NOT be reused for these labels.
Entry/offset markers bracket execution, not full rawlog or exact failure proof;
tracing can affect timing. Off-path firmware calls have different offsets.

Exact v2 image guard in progress/final independent validation pending.
LAST INSTALLED BOOT_A STILL STOCK; no hardware observer/trial active.
If all checks pass, lynx_boot_a_refclk_v2_probe_trial.py --flash-linux --reboot.
On return fresh ACL/LK then --restore-stock/no reboot. On no return within
240s stop for physical Fastboot. Next read-only query must use this exact new
token/event mapping and validated runtime; do not report old function labels.

### Corrected reference-clock probe ACTIVE; stock undo pending

Exact guard1792000112061067612 PASSED. Independent refclk-v2-probe-validation
PASSED all preserved kernel/modules/probe/reset/metadata/payload checks,
exact offset definitions/native activation/probe-safety and AVB policy.
Trial logs/boot-a-refclk-v2-probe-trial-1792000293405053079.json accepted
boot_a send/write and one normal reboot; passive USB observation240s active.
LAST INSTALLED BOOT_A REFERENCE-CLOCK V2 imageb4a50542..., NOT STOCK.
On return fresh USBACL/read-only LK then
python3 /noobia/lynx/tools/lynx_boot_a_refclk_v2_probe_trial.py --restore-stock
No reboot. If no return stop for physical Fastboot. No concurrent hardware test.

While observing, built read-only artifacts/busybox-retained-refclk-trace-query-v1
SHA4eec20add7e57d70c5f29b11f02b7f726e8cc8ff24be1395aa738605c39bccf5,
ramdisk1647360. Same bounded reader runtime as previously proven query299c...,
but exact new reference token69adf9d14707d848063b861b8f248748 and event meanings.
All9events UFS-specific; ID8 is a kretprobe return marker (retval not fetched by
this query). Reader code/34 prefix/reset/limits unchanged; separate image/token
and native/control/guard tests prepared and running. Timing math19slots unchanged.
Final independent validation NOT YET run. Do not flash until all checks pass.
No raw log download or exact failure instruction claim. Preserve all versions.

### Finer probe did not return; STOP for physical Fastboot

Trial1792000293405053079 completed240s passive observation with no Fastboot
return and no native SSH. Do not infer marker execution, exact hang, firmware
failure or pstore persistence from non-return. LAST INSTALLED BOOT_A STILL
REFERENCE-CLOCK V2 b4a50542..., STOCK UNDO PENDING. Hardware work stopped.
User must return Lynx to Fastboot; use actual USB state, not ok as confirmation.
On return await USBACL exit0, save supported read-only LK then verified
lynx_boot_a_refclk_v2_probe_trial.py --restore-stock, awaitexit0/no reboot.
Only then finish validation/run the read-only finer-marker query.

Prepared query host30case corpus1792000506870335635 PASSED; exact query guard
1792000505999940123 PASSED. Native test already launched before observation
ended; completion receipt pending at this state entry. Independent validation
still pending. No further phone commands issued. All sources/images/tests and
raw receipts retained under /noobia/lynx. No active phone observer remains.

Already-running native readback test1792000505651678414 completed PASS after
observation ended: real ARM64 parser/synthetic matchingmarker4, basefail16,
empty0, own capsule hashes/sequences, three fake resets, no exception/clean
poweroff. No VM or phone observer remains. Final independent query validation
still pending; no query flash issued. Physical Fastboot required next.

### Physical Fastboot recovered; finer probe restored and readback ACTIVE

On user ok go, actual Fastboot USB001/016 observed. USBACL request completed
exit0 after waiting; no phone command sent before completion. Supported LK
logs/pllk-1792000751869227173.json saved(raw306599bytes), label?/NONRST20000000/
wdt0; not evidence of a particular hang or crash. Stock undo
logs/boot-a-refclk-v2-probe-trial-1792000771987963063.json accepted boot_a
send/writeOKAY exit0, no reboot/other writes. Stock was installed before query.

Final validate_retained_refclk_image.py --count34 PASSED: query4eec20ad...,
exact reference b4a50542... token69adf9d14707d848063b861b8f248748, correct9
checkpoint/return meanings, native/control/guard/bounds/timing/geometry/modules/
kernel/metadata/supplement/model checks. Reader has no new main UFS activation.
Now lynx_boot_a_retained_refclk_trial.py --flash-linux --reboot observing270s.
LAST INSTALLED BOOT_A QUERY once write accepted; stock undo pending afterward.
On return fresh USBACL/LK then same tool --restore-stock(no reboot), awaitexit0.
On no return stop for physical Fastboot. Interpret last selected retained marker,
not exact CPU stop; checksums are not authentication/complete stream proof.

### Finer retained trace reaches request-store boundary; stock restored

Read-only query logs/boot-a-retained-refclk-trial-1792000799665556758.json
returned161.75437212399993s, field4, residual0.079129186001s. Last token-specific
checkpoint in selected checksum-valid reference record is before on-path
request-register store(+0xa0). No later marker retained in that selected sample.
Reaching this boundary on the audited control path is after the firmware call;
do not blame authentication/SMC non-return based on old entry-only evidence.
Still not exact stop proof: logging/tracing can affect execution, and no full
sequence/rawlog or guaranteed newest boot across files retrieved. Subsequent
register store or trace completion is the next boundary to investigate.

Supported LK1792001195573833013 matches lk/NONRST28002003/wdt2. Stock undo
logs/boot-a-retained-refclk-trial-1792001251973574639.json accepted send/write
OKAY exit0/no reboot. LAST INSTALLED BOOT_A STOCK, Fastboot USB001/017.
No observer active. Native SSH/Wi-Fi/storage block access still unproved.

Saved stock startup/module/merged-DT audit docs/ufs-stock-startup-audit.json
and local primary sources startup-clk-bringup.c/startup-mtk-scpsys-bringup.c/
startup-clk-mt6983.c at published commit81ec42ad...(not exact stock commit).
All5 UFS-requested clocks are from loaded topckgen provider. Stock modules.load
also loads clk-bringup.ko before UFS. Sole matching merged-DT target is
/clkitg/bring-up, compatiblemediatek,clk-bring-up, okay,23listed clocks from
clk26m/infracfg_ao/topckgen, including extra infra and top clocks omitted from
UFS own5clock requests. Source enables these clocks via normal clk API; errors
are logged/ignored, so insertion is not proof of every clock enabled. No
matching scpsys bringup/postao node found in merged DT; no reason to add that
module yet. Firmware-helper hypothesis not established; stock load order places
tinysys-scmi after UFS. No added module or register force performed by audit.

Next verify exact stock clock helper match table/ABI and runtime DT target,
then consider one clock-helper-only change to controlled UFS boot_a trial.
Require host/native/guard/image validation and preserved stock undo as usual.

### Audited stock clock helper added behind exact-target guard; trial ACTIVE

Exact clock helper audit PASSED: moduleSHA
4b62b692837be57cc9aab66136dec5d772840c8f572c37c20c59bda979216823,
same g311738fbb5a8/vermagic, no declared dependencies/shared imported CRC
conflicts; exact OF table onlyclk-bring-up/clk-post-ao. Merged DT has only
/clkitg/bring-up (simple-bus parent), clockpropertySHA
c6c820b927cb362d545b5798b35dec002e60f50805a78d4cc81ad7e90b698e9b.
Stock helper enables23 listed clocks through normal kernel API, including
bus_aximem_sel (top clock248) outside UFS own5 clocks. No manual register force.
Not proof this is the missing dependency or that all clocks enabled.

Prepared artifacts/busybox-stock-clock-helper-probe-v1 SHA
b161edddb4a1a6a2e572f16298397f162d14f2d3e888220e58b576c5c4c0fe76,
ramdisk1648471, session739ab92bd0a0f1d0d916d126ba1c7f3e.
First40 unchanged; UFS matching guard set before helper. Helper guard requires
notalreadyloaded, exactlyone unbound compatible/path target, exact clockproperty
and actual .ko SHA before load. Supplied by unchanged stock vendor ramdisk.
After insertion require driverbring_up bound and read-only framework
bus_aximem_sel prepare/enable counts positive, else no UFS probe requested.
Framework counters are not actual hardware measurements. Helper ignores
individual clock errors. No new scpsys bringup, rawregister poke, partition
storage/calibration write, firmware logic change or authentication bypass.
All original module/kernel/recovery bytes and reference-clock traces preserved.

Stage516:1beforehelperload,2loadreturned,3bound/counterspositive.
Existing outcomes0..9 unchanged;10helperguardrefused,11helperloadfailed,
12helpernotbound,13buscountermissing/zero => no UFS probe requested.
14five-second slots120..185, tolerance2s,90s sample,240s observer,one normal reset.
Native exacthelperABI+ARM64guard13cases1792002337470437103 PASSED, own valid
hex/cleanpoweroff/no exception. Combined supervisor13cases1792002706992137223
PASSED. Exact image reset guard1792002708082641051 PASSED. Timing57cases PASSED.
Final independent stock-clock-helper-probe-validation PASSED preserved-source/
ABI/DT/native/control/guard/timing/geometry/metadata/payload/boot-policy checks.

Now lynx_boot_a_stock_clock_helper_probe_trial.py --flash-linux --reboot:
on acceptedwrite LAST INSTALLED BOOT_A CLOCK-HELPER DIAGNOSTIC, STOCK UNDO PENDING.
Passive observer240s, no simultaneous hardware test. On return fresh USBACL/LK
then same tool --restore-stock(no reboot), awaitexit0. On no return stop for
physical Fastboot. Readback must use this exact new token, helper phase516 and
finer9 event meanings; do not reuse old token. Still no verified Wi-Fi/SSH.

### Stock clock helper proves controlled UFS binding; Wi-Fi v7 returns early

Clock-helper hardware trial logs/boot-a-stock-clock-helper-probe-trial-1792003167463063951.json
returned 141.72383403300046 seconds, decoded field0/residual0.10966727699997:
ufshcd-mtk bound after exact clock helper guard/cached framework counters passed.
Block-device reads, payload access, calibration, Wi-Fi and SSH were not thereby proved.
LK1792004030064469099 normal reset; stock restore1792004226629890074 succeeded.

Wi-Fi v7 preserves the physically successful UFS override/helper/traced controlled
probe flow, base34/storage7, V5 payload at24MiB and unchanged radio/credentials.
Candidate SHA9a17b8e72e8e8fe8928f551fcf593cee1d19a712affe498f23f637e7ac4da00c,
token135562a3878163138979301c76b64536; required native journals/exact-image guard/
independent image validation passed before trial1792006188424181913.
Returned early to Fastboot, no UDP beacon or verified SSH. Cause UNKNOWN.

Read-only supported LK capture1792006688435032783 succeeded, reset fromlk,
NONRST_REG2=28002003, wdt2 matches deliberate reset. Stock boot_a restore
logs/boot-a-wifi-v7-trial-1792006699503237717.json completed send/write OKAY exit0,
no reboot. LAST INSTALLED BOOT_A STOCK; Fastboot USB001/019. Other partitions
unchanged. Old collector PID121820 received targeted SIGTERM to free UDP5514.

Preparing separately preserved busybox-retained-wifi-v7-query-v1 with proven34
prefix only, no storage PHY/main-controller activation, block reads or radio.
SHA8af0ebdcc356256a540dfdaa5fd5eff27bd9220737c880782d9ef53eb5becc22,
ramdisk1646991. Reads at most8 regular nonsymlink retained kernel files, first1MiB
each; exactv7token/checksum; prefers failure capsule over major phase and reset
chatter, latest sampled byte order within same priority, first tied file.
One selected record only; not newest-boot/authentication/full-sequence proof.
19slots120+5code, sample90s, tolerance2, observer270s; only one normal reset.
Host/native/exact-image checks in progress; DO NOT FLASH until independently
validated. This query distinguishes bootstrap151/152/153/154/other, Wi-Fi worker
failure, or retained major phase. No live SSH shell has been established.

### Wi-Fi v7 retained query found no available valid capsule; stock restored

Readback native test1792006940509638132, host selection43cases1792006939583468896,
exact image guard1792006940033614000 and independent validation PASSED.
Hardware trial logs/boot-a-retained-wifi-v7-trial-1792007090552374937.json
returned141.73541490199568s, field0/residual0.09808640800474677: no checksum-valid
v7 reference capsule in selected bounded retained files. This does not show
whether v7 emitted no capsule or whether persistence/retention/truncation lost it.
No failure phase identified. LK1792007777401711061 succeeded. Stock restoration
1792007836629556672 accepted send/writeOKAY exit0, no reboot. LAST INSTALLED BOOT_A
STOCK; USB001/020. No live observer or radio/SSH collector active.

Readback semantic erratum: code5 includes bootstrap completionstatus0 as well as
unclassified bootstrapstatus, because diag-hooks emits stage254 on success too.
Do not interpret code5 as definitely failed. This hardware result wascode0,
so unaffected. Preserve existing artifact/tool rather than silently rewriting
historical codebook. Any future reader should explicitly distinguish status0.

Preparing bootstrap timing diagnostic v1 (a9c233c6aefbae80e2e9cd1fabbb1dcda8cdac3119d9ea58bc5e95b73c96802a),
ramdisk1647665. Preserves every v7 stock module/guard/helper/trace/payload byte,
kernel/cmdline/AVB/footer; only init and fresh token differ. Stops before radio.
Both bootstrap success and original failure/deadline paths use one normal reset,
timed from saved RAM start at240+5code, max275s; observer360s. Eight outcomes:
0payload verified/extracted,1base151,2storage152,3partition153,4payload154,
5other numeric result,6resultmissing/deadline,7malformedresult.
Native ARM64 BusyBox10cases1792008924489274967 PASSED incl all eight result slots,
bad start/clock refusal and exactly8 fake resets. Exact image guard1792008925112359144
PASSED (failure guardobserved, no reboot); independent validation IN PROGRESS.
No retained-log dependency; don't flash before validation. Stock undo ready.

### Bootstrap timing image validated; hardware observer extension ACTIVE

Independent bootstrap-timing-validation PASSED parentv7/native/exact-image guard/
exact startup delta/archive/kernel/cmdline/metadata/payload/model/57timingcases.
Initial timing corpus exposed floating-point exact2s-boundary error; decoder now
rounds residual to nanoseconds (not meaningful tolerance expansion), corpus passes.
Hardware trial logs/boot-a-bootstrap-timing-trial-1792009047412492624.json
accepted boot_a send/write OKAY and one reboot. LAST INSTALLED BOOT_A BOOTSTRAP
TIMING DIAGNOSTIC; STOCK UNDO PENDING. Radio is not started by this image.

Runner copied270s observer by mistake despite validated manifest360s; caught
while phone still running, before observer expires. Separate passive continuation
tools/extend_bootstrap_timing_observation.py inherits real original USB departure
events and records fresh sysfs until reboot+360s; NO additional phone commands.
Separate extension receipt retains seedSHA/source/gap/provenance. Original trial
tool/receipt retained. Future tool lynx_boot_a_bootstrap_timing_v2_trial.py corrects
both host deadline and displayed bound to360s. Await BOTH running observers;
use extended receipt for timing if original270s misses return. On return fresh
USBACL/supportedLK/stock restore(no reboot); on unexpected return or no recovery
stop for physical input. Do not infer physical non-interference from silence.

### Direct bootstrap timing identifies own boot_a payload failure

Original270s observer missed return, retained as-is. Passive extension
logs/bootstrap-timing-observer-extension-1792009132098377596.json captured return
281.905898555s, field4/residual0.072397245: bootstrap child status154 (own boot_a
payload read/verify/extract failed). Source image guarantees base34/storage7,
UFS exact guard/helper/controlled binding and partition discovery preceded it.
Still no successful physical block read, extracted payload, Wi-Fi or SSH proof.
LK1792009455462475407 normal lk/NONRST28002003/wdt2. Stock undo
logs/boot-a-bootstrap-timing-v2-trial-1792009469090148227.json accepted send/write
OKAY exit0/no reboot. LAST INSTALLED BOOT_A STOCK; USB001/021. Both observers done.

Native payload test emulated-native-payload-loop-1792009523537673393 PASSED:
same stock kernel/real ARM64 BusyBox/actual loop block I/O,64MiB candidate image,
block remained read-only, own payload hash verification/gzip/cpio extraction
succeeded and Dropbear/WPA/radio module files present. Partition metadata fixture
only; no physical UFS claim. Payload reader SHA2f7787ee... saved. Thus generic
command/extraction chain works in this environment; hardware-specific failure
still could be discovery/duplicate labels/device nodes/capacity/ioctl/read/hash.

Prepared separately preserved busybox-payload-timing-v1 SHA
9df9229dba14a1b29e17a5bcdb8c34fb813682998a63ff57718ed1bb7f6f9226,
ramdisk1647730. Only init/token differ from prior bootstrap image;7RAM checkpoints
before enumeration,blocknode,capacity/RO,metadata,rawread/head,hash,gzip/cpio.
No block/calibration writes or radio activation. Direct9slots240+5code:
0success,1enum/unique/name,2missingblocknode,3capacity/RO,4metadata,
5read/head,6hash,7gzip/cpio,8otherbootresult/deadline/badprogress. Observer360s.
Native classification10cases1792009762763455215 PASSED, exact-image reset guard
1792009763087223729 PASSED. Real loopblock instrumented reader1792009763482688016
PASSED hash a760ca8ab...; adds checkpoints without breaking reader. Final independent
validation IN PROGRESS. Stock undo ready; do not flash before validation.

### Payload step image validated; hardware trial ACTIVE

payload-timing-validation PASSED parentbootstrap/v7 checks, exact executable delta,
all protected archive/kernel/cmdline/AVB/payload bytes, native classification,
real loop block reader, exact-image reset guard,63timingcases and boot model.
Now logs/boot-a-payload-timing-trial-1792009882196341626.json accepted boot_a
send/write OKAY and one reboot; passive observer360s (corrected from outset).
LAST INSTALLED BOOT_A PAYLOAD STEP DIAGNOSTIC; STOCK UNDO PENDING.
No radio/calibration/SSH activation. Await complete return and step interpretation;
then fresh USBACL/LK/stock restoration(no reboot). Preserve all source/artifacts.
Native module startup unchanged; physical payload access remains unproved.
Source investigation/provenance saved docs/PAYLOAD-READ-INVESTIGATION.md.

### Physical raw read and checksum verified; reproduced extraction conflicts fixed locally

Payload step trial1792009882196341626 returned297.0393696050014s, field7,
residual0.205868295. Instrumented code ensures raw boot_a read and exact payload
SHA256 verification passed before gzip/cpio step7. Physical extraction still
failed. LK1792010281876352783 succeeded; stock undo1792010288936728706 accepted
send/writeOKAY exit0/no reboot. LAST INSTALLED BOOT_A STOCK; USB001/022.
No radio/SSH proof and no active phone observer or collector.

Native stock-vendor payload test1792010274494168590 reproduces cpio exit1:
can't remove old file vendor/firmware: Is a directory. Actual stock vendor
ramdisk has a directory, original payload tried symlink ../lib/firmware.
Bare-root native tests missed this because they omitted vendor ramdisk.
All subsequent extraction tests include actual vendor ramdisk.

V8 unflashed intermediary SHA8c8879b5... was rejected before any hardware use:
supplement was encoded with ramdisk LZ4 instead of required userspace gzip.
Preserved as-is, flash_eligiblefalse. V9 gzip directory repair SHA0b0da995...
never flashed: closer vendor test1792010574461580990 failed on odm/etc. Source
root parent audit1792010793968083709 identifies EXACT stock /odm/etc symlink to
/vendor/odm/etc, target absent. /odm itself is a directory (earlier conversational
shorthand saying /odm symlink was imprecise). Both failure receipts preserved.

V10 SHA bd0f541c93507b296865699e7c972c9468600bdc516e2bfed234dbb12497606f
ramdisk1647321/payloadgzip12239410. Preserves v7 init/kernel/cmdline/modules/
credentials; only token,payload count/hash and supplemental layout change.
vendor/firmware becomes directory with11 byte-identical firmware mirrors from
lib/firmware. Relocates only odm/etc entries beneath vendor/odm/etc; retains stock
odm/etc alias. No stock partition data writes involved in these RAM layouts.
Native exact-vendor loop read/extract1792012854305137664 PASSED, preservedfirmware
directory and resolvedODM alias checked. Native journals1792012855485856780
PASSED allguards/order/failure/separatechecksummedjournals; exact-image guard
1792012856554390994 PASSED(no reboot). Independent validation finishing.
V10 not flashed yet; stock undo ready. Corrected physical extraction and Wi-Fi/
SSH remain unproved until a controlled hardware trial.

### Corrected Wi-Fi v10 hardware trial starting

Independent wifi-v10-image-validation PASSED exact first-stage metadata/token-only
delta, unchanged kernel/init/modules/credentials, protected AVB/footer boundaries,
gzippayload,11exact firmware mirrors, exact ODM relocation, actualstockvendor
loop extraction, journals/resetguard/model/pinned SSH self-test. Parent directory
vendor is added by put() helper; validator now explicitly requires mode40755,
uid/gid0 and empty directory data rather than omitting this expected addition.

Noobia interface wlx40a5ef5f66f1 verifiedUP192.168.100.106/24. Matching600s listener
logs/wifi-v10-contact-1792013181798462283/result.json started. Now running
lynx_boot_a_wifi_v10_trial.py --flash-linux --reboot with that live listener.
On accepted boot_a write LAST INSTALLED BOOT_A WIFI V10; stock undo pending
unless pinned native SSH identity is proved and fallback cancel acknowledged.
Passive USB observer600s; no additional handset commands while active. Need
actual trial receipt/fresh USBACL/LK/restore if Fastboot returns; if no return
stop for physical input. Existing kernel/bootloader/recovery/slotB untouched.

### Corrected-layout v10 returns without SSH; stock restored; direct network timing v11 prepared

Wi-Fi v10 trial logs/boot-a-wifi-v10-trial-1792013198100225292.json accepted
send/write/reboot, returned Fastboot without UDP beacon or native SSH. Physical
cause UNKNOWN; native vendor layout fixes pass but actual physical extraction
success not inferred from that fact. Supported LK1792013319715011280 saved;
stock restore logs/boot-a-wifi-v10-trial-1792013336004299173.json send/writeOKAY
exit0/no reboot. LAST INSTALLED BOOT_A STOCK; USB001/023. CollectorPID149959
targeted SIGTERM; no active phone observer or network listener after this trial.

Prepared Wi-Fi v11 SHA4aad96c499317fa7f6d46371657a8e8bb93043b99de6627f801c5508f40a1033,
ramdisk1648120. Preserves correctedV10 payload/kernel/cmdline/modules/credentials.
Original native reboot ELF copied byte-for-byte to bin/boot-proof-reboot-native;
original call path becomes RAM-only shell timing reporter. First-stage init adds
only common startuptime capture before bootstrap. Caller supervision/SSH fallback
cancellation unchanged. Known watchdog/reboot-mode guard still precedes reporter.
No extra storage/radio controls. On failure one normal native reset at480+5code,
max600s from captured start; host720s. Allslots later than bounded180s bootstrap+
240s Wi-Fi supervision. Code0worker0/nohostack,1..16worker131..146,
17otherworker,18workermissing,19otherboot,20..23boot151..154,24bootmissing.

Native25classificationcases+badstart/clock/refusal1792013546462034873 PASSED.
Real loopblock exactvendor extraction1792013544834278794 PASSED incl preserved
firmwaredir/ODM alias. Native guarded supervision+journals1792013545960294659
PASSED. Exact-image resetguard1792013545648084937 PASSED(no reboot).
Independent wifi-v11-image-validation currently finishing incl176timingcases,
exact first-stage delta/nativehelperhash and protectedbytes. NOT FLASHED YET.
Stock undo ready. Physical Wi-Fi/SSH and precisev10failure remain unproved.

### Wi-Fi v11 validation passed; direct result trial ACTIVE

Independent wifi-v11-image-validation PASSED parentV10 exactpayload repair,
unchangedprotectedbytes/nativehelper, exactstart-anchor/timingwrapper delta,
nativeclassification/journals/vendorloop/resetguard,176timingcases and pinned
SSH/model checks. Matching listener
logs/wifi-v11-contact-1792013706056953218/result.json started720s.
Hardware logs/boot-a-wifi-v11-trial-1792013739729132952.json accepted boot_a
send/writeOKAY and one reboot; passive observer720s. LAST INSTALLED BOOT_A
WIFI V11; STOCK UNDO PENDING unless nativeSSH proved and fallbackcancelack0.
No contact seen at last snapshot. Await direct field or verifiedSSH; no
additional handsetcommands while observer active. On returnedFastboot fresh
USBACL/LK/stockrestore(no reboot); on unexpectedrecovery stop for physical input.
EXPERIMENT-INDEX refreshed114receipts, no parseerrors, currentV11write recorded.

### Wi-Fi v11 reaches station power; stock restored; clock supplier investigation

Wi-Fi v11 trial1792013739729132952 returned546.1061447219981s, field9,
residual0.727356588: Wi-Fi worker139/station command failure. On this exact control
path bootstrap payload verification/extraction, read-only factory calibration,
radio-module insertion, MT6983 chip ioctl and calibration submission returned
success first. Module insertion is not proof of every hardware supplier bound.
No WLAN/association/DHCP/SSH proof. Interpretation remains conditional on normal
reset evidence/physical non-interference; software timing alone isn't raw log.
LK1792015057103459539 succeeded; stock restore1792015204936747053 accepted
send/writeOKAY exit0/no reboot. LAST INSTALLED BOOT_A STOCK; USB001/024.
Listener720s ended with no verified SSH; no observers or collectors active.

Source says S already attempts power-on plus station/P2P setup, so no speculative
1+S retry. Exact stock wmt module SHA96df60a8... has6diagnostic strings verified
by station-error-string-audit-1792015402390510530. Preparing bounded same-boot
kernel snapshot after an exact token-bound station marker, then direct timing
of last recognized diagnostic. No raw retained/fullstream claim.

Kernel CONFIG_MTK_CLKBUF=m; our startup omitted clkbuf.ko and mt6685-core.ko,
which stock modules.load includes at124/132 after UFS. Source MT6685 core creates
clock-buffer/consys child devices. MergedDT has uniqueMT6685 parent,
MT6685 clock-buffer child, srclken-rc target and clock_buffer_ctrl configuration;
Wi-Fi output XO_BBCK2. Initial inventory search used incomplete name patterns;
corrected inventory1792016313460387074 shows actual clock_buffer/srclken targets.
Stock-radio-clock-audit PASSED exact binaries/vermagic/OF tables/closed declared
dependencies/shared imported CRCs and18criticalDT properties. Missing providers
are a hypothesis, not independently proved physical cause. No helper loaded yet.
Exact supplier modules supplied by unmodified vendor ramdisk, not rebuilt.

Prepared radio-clock-guard.sh: reject preloaded helpers, missing/changed18property
map, wrong modulebytes/ambiguous,busy,wrong-node targets; register only stockMFD
then stockclkbuf; require canonicalMFD/clock/RCbindings. No unbind/register-force
or partition/calibration write. Binding isn't independent clock measurement.
Station parser ignores logs before last exactcurrenttoken marker and transport
reports one lastmatching diagnostic, not complete log or exact CPUstop.
PreparingV12 with these guards/diagnostics in supplementalRAM files. NoV12flash
before nativeABI/fixtures/control/image checks. Stock undo ready.

### Explicitly paused for the night — V12 prepared, never flashed

Noob requested a pause; resume only after their next instruction. All trials,
collectors and native checks have finished. No V12 listener or hardware trial
was started. LAST INSTALLED BOOT_A remains STOCK, restored successfully by
logs/boot-a-wifi-v11-trial-1792015204936747053.json (no reboot).
Stock boot SHA256: a67f03d7b826b834c23653b67eaa6efa971eb70ef8af19eee4d33fb5fc7fe995.

V12 candidate prepared and independently validated, NEVER FLASHED:
linux-port/artifacts/busybox-wifi-ssh-twostage-v12/nord3-busybox-candidate.img
SHA256: 1e51aeff4eae67f50c5bce85986d7f423a14c6274332b99d2e64015288f8b73b.
Independent receipt: linux-port/docs/wifi-v12-image-validation.json PASSED.
Native station classification, supplier module ABI, actual vendor loop extraction,
reset guards and host guard/parser fixtures passed. These are local checks, not
physical Wi-Fi proof. V11 reached station power; association/DHCP/SSH remain
unverified. V12 adds guarded stock clock suppliers and bounded station-failure
diagnostics while preserving the stock kernel and restoration procedure.

Tomorrow: inspect current USB/state and receipts first. After user resumes,
start matching V12 contact listener with 780-second lifetime, then use guarded
V12 boot_a trial only with its fresh preflight and active collector receipt.
Preserve slot B, bootloader and recovery partitions; restore stock boot_a on
failed trial if Fastboot is available, and stop on unexpected recovery behavior.

### Resumed: V12 hardware trial active

User requested continuation. Fresh Fastboot identity/layout checks passed:
logs/fastboot-preflight-1792080980573228473.json. Independent V12 validation
passed again. Collector logs/wifi-v12-contact-1792080995509261151/result.json
started with 780-second bound. Trial logs/boot-a-wifi-v12-trial-1792081041410152375.json
accepted boot_a write and reboot; passive observer active. LAST INSTALLED BOOT_A
V12 until a subsequent stock-restore receipt. Stock undo pending unless pinned
native SSH and cancellation acknowledgment succeed. No other partitions written.

### V12 completed: station power failure, stock restored

Trial1792081041410152375 returned Fastboot after641.772544783s, field28,
residual0.060956527s: last current-attempt station diagnostic power-on failed.
This implies exact target guards and canonical clock-provider bindings passed
first, not that clock outputs were independently measured. No UDP events/SSH.
LK1792081735305073565 succeeded; NONRST_REG2=0x28002003, wdtstatus0x2,
consistent with deliberate software return. Stock undo1792081742054266790
accepted boot_a send/write OKAY exit0, no reboot. LAST INSTALLED BOOT_A STOCK.
Collector ended at deadline; no active trial/listener. Preserve raw receipts.
Next investigate inner wlanProbe failure/timeout using bounded same-boot log,
without changing radio startup or adding power retries.

### V13 diagnostic-only follow-up active

Exact stock module literal audit1792081876604900695 passed. Added
power-failure-parser.sh with current token/attempt boundary and committed
inner diagnostic only before generic power failure. Reports timeout, invalid
callback, or raw wlanProbe reason0..7 (source labels not binary-enum proof).
25 host isolation/malformed/order cases passed1792081920927832261. Native
39result paths/invalid-clock checks passed1792082058756757195; exact-image
reset guard passed1792082139547154500. Independent wifi-v13-image-validation
passed. CandidateSHA3b7d7962c8526e01b60f953f5f6b660e10cc6d599f7539d290f03857147165bb.
Only parser/session token differ from V12; startup/payload/kernel unchanged.
Trial1792082269466593399 accepted boot_a write and reboot, observer780s
active. Collector wifi-v13-contact-1792082253154054090/result.json active.
LAST INSTALLED BOOT_A V13, stock undo pending unless pinned nativeSSH+ack.

### V13 completed: power-control timeout; stock restored

Trial1792082269466593399 returned Fastboot after626.809410853s, code25,
residual0.024090457s: current-attempt power-control timeout diagnostic before
generic power failure. This is indirect timing evidence, not a complete log.
No network beacon or SSH. LK1792083654392223770 succeeded, NONRST_REG2
0x28002003 and wdtstatus0x2 consistent with software return.
Stock restore1792084058209819698 accepted boot_a send/write OKAY exit0,
no reboot. LAST INSTALLED BOOT_A STOCK. Collector ended; no hardware test active.

Stock diagnostic literal inventory1792082365053606565 and exact function
disassembly1792082568102840820 preserved for offline review. Source was a
reference, not exact stock build provenance. Exact power controller waits
0x9c4 ticks, emits timeout string with argument10, returns false on timeout;
worker has an inlined status==1 sleep loop before indirect probe callback.
Do NOT infer which wait timed out from code25 alone.

Next useful diagnostic: capture the named kernel worker's /proc/PID/stack
immediately after timeout, using standard read-only procfs (no kprobes needed).
Stock kernel CONFIG_PROC_FS/STACKTRACE/KALLSYMS/FRAME_POINTER are enabled.
An exact-module stack offset can distinguish the pre-calibration sleep loop
from a callback blocked deeper in driver initialization. Must verify binary
offsets and handle absent/ambiguous workers/unavailable stack explicitly.

### V14 worker-stack diagnostic active; synchronized launch fixes approval gaps

V14 imageSHA5bc287a9fea447edfe83eeb284d8371ea0ac093f3a17f74e3db66bb171cedded,
ramdisk1648310, supplement12243212. One unchanged station attempt; on failure
save immediate dmesg then bounded read-only /proc/PID/{stack,status,wchan} for
the exact named Wi-Fi worker. No runtime tracing or module patching. Timing
parser in verified supplement reports saved stack category only when previous
parser proves current marked power-control timeout. Slots9/35 not produced.
Independent wifi-v14-image-validation PASSED; procfs actual stockkernel test
1792084670876055960, host19cases1792085033599447610, native38classification
1792085116355944289, vendorloop1792085116855979394, resetguard1792085116492272075.
Exact binary wifi-worker-wait-audit independently verifies pre_cal_ongoing byte,
300ms msleep call and return offset0x214 in mtk_wland_thread_main. It does not
prove why calibration remains pending. Captured stack is a post-timeout sample.

First attempt1792085637546733376 REFUSED before phone contact/write: execution
approval delay made collector older than90s. Preserve this guard failure. Old
collector PID20435 stopped after exact ps verification; session26583.
New tools/run_wifi_v14_trial.py launches fresh listener AFTER approval and then
fixed trial without another approval gap. It owns collector lifetime and
terminates its own listener after trial/failure; native SSH diagnostics get90s.
Active collector logs/wifi-v14-contact-1792085809501301767/result.json.
Active trial logs/boot-a-wifi-v14-trial-1792085818708701369.json accepted
boot_a send/write OKAY and reboot. Observer780s. Unified runner session56157.
LAST INSTALLED BOOT_A V14; stock undo pending unless pinned SSH+ack succeeds.
No commands to handset while observer active. After returnedFastboot renew
USBACL, capture LK/reset evidence, then verified stockrestore with no reboot.

### V14 completed: readable worker stack in connectivity power; stock restored

Active trial1792085818708701369 completed: return641.718921345s, code28,
residual0.114579965s. Current marked timeout evidence plus unique readable
Wi-Fi worker stack included connectivity power function(s). It did NOT match
the exact pre_cal_ongoing sleep return0x214. Raw stack remains in phone RAM,
not retrieved to host; only classified timing result is available. No UDP/SSH.
Unified launcher1792085809472293419 ended and stopped its owned collector.
LK1792086530240741463 captured; NONRST_REG2=0x28002003, wdtstatus0x2 consistent
with deliberate reset. Stock restore1792086567796848435 send/write accepted
exit0/no reboot. LAST INSTALLED BOOT_A STOCK; USB001/008. No active phone trials.

Pinned manufacturer sources saved docs/wifi-wait-sources-1792085962321757460/:
axi.c, pre_cal.c, conninfra_core.c, each manifest-hashed. Reference source has
up-to60s pre-cal callback registration wait, while exact stock power controller
times out after10s. This is a timing-mismatch hypothesis, not yet proved root
cause. Exact worker normal idle return0xe4 independently verified by
wifi-worker-idle-audit; actual Wi-Fi module name wlan_drv_gen4m_6983.
Next candidate could passively await the initial asynchronous request after
its timeout, then permit ONE additional normal S command ONLY with two stable
samples of the exact worker-idle stack and a driver-bound Wi-Fi netdev. No
retry while worker busy, no forced completion/calibration flags, no extra radio
drivers or power-register writes. Needs implementation and host/native tests
before any flash. Preserve first timeout log/stack and final readiness evidence.

### V15 guarded asynchronous completion + faster timing trial ACTIVE

User requested shorter waits and batched tests, retaining correctness first.
CandidateSHA c08d19beb54ef6400912651539d6ce9f510632a94d04180f30b88114d48768f2,
ramdisk1648369, gzip12244100. New wifi-station-async.sh permits an initial normal
S request and at most one completion S request, only after current marked
timeout, subsequent current-marked wlanProbe success, two stable exact worker
idle stacks0xe4, samePID/ifindex and phy80211/netdev type1 bound to exact stock
wlan_drv_gen4m_6983 module. Passive wait bounded90s. No overlap, forced flags,
new radio drivers, register writes or calibration writes. First failure files
preserved with .first suffix; current failure and async dmesg remain in RAM.
Host20 +actual stockkernel ARM6readiness cases passed1792086852323476899;
station-flow4cases passed1792087217429583161 (one/two request bound and original
failure preservation). Parent clock/module/kernel/credential bytes unchanged.

Timing now120+5*code, except slot9=525s. If chosen early slot has less than3s
remaining, report only late-result slot9; if that slot also missed, refuse
reset rather than emit false detail. Decoder lynx_fast_wifi_timing.py pins
this exact grid. Observer/listener660s. Native batched38normal+1late reset,
invalid clock/start and missed-all-slots refusal1792087237962666563 PASSED;
vendor block/extract1792087238191491057, exact resetguard1792087238473370041,
independent wifi-v15-image-validation with280decoder boundary cases PASSED.
Validation reuses pinned V14image+passedreceipt, avoiding unchanged recursive
test/model reruns. Legacy timing comment about all slots after420s is obsolete;
the explicit new runtime margin/late-slot guard is authoritative.

Synchronized launcher tools/run_wifi_v15_trial.py started after approval.
Collector logs/wifi-v15-contact-1792087399255602486/result.json. Runner session
75052; inspect its output for exact trial receipt/write status before assuming
V15 was installed. Stock undo prepared, only boot_a allowed. No additional
handset commands during observer. On returnedFastboot: freshACL, LK, stockundo
no reboot unless pinned native SSH+ack succeeded. Native Wi-Fi/SSH still unproved.

### V15 completed faster: worker waiting in firmware loader; stock restored

Trial1792087400379311204 accepted boot_a write/reboot and returned in276.009155636s,
code27, residual0.824345674s on new fast grid: current marked control timeout and
readable unique worker stack including firmware loader. No UDP/nativeSSH. This
is a sampled firmware-loading wait, not proof of a particular missing file or
whether a second station call occurred. First-failure/current async diagnostics
remain RAM-only, not retrieved. Faster result roughly4m36s versus prior10m42s.
Launcher1792087399226788088 completed and stopped its collector.
LK1792087763998089421 succeeded, NONRST_REG2=0x28002003/wdtstatus0x2 consistent
with software return. Stock restore1792087772736487910 accepted send/write OKAY
exit0/no reboot. LAST INSTALLED BOOT_A STOCK; USB001/009. No phone trial active.
Stock CONFIG_FW_LOADER_USER_HELPER[_FALLBACK]=y, CONFIG_UEVENT_HELPER=n. Native
mdev -s alone cannot imply a running firmware-uevent service. Next audit exact
stock firmware coverage/search paths and identify pending request name; do not
assume wrong firmware bytes or bypass calibration merely from this wait.

### V16 standard firmware-event service trial ACTIVE

Offline coverage inventory1792087868374880314: 11firmware files embedded;
1883stock firmware files/412054628bytes inventoried. No absent simple literal
matches, templates remain dynamic. Exact BusyBox1.37.0 SHA999cb969... supports
mdev -df netlink daemon and firmware loading. Actual ARM stockkernel daemon
test1792088009610432217 PASSED. Batched actual BusyBox synthetic sysfs firmware
protocol test1792088104605085036 PASSED: correct file bytes delivered, loading
sequence1then0, explicit-1 for absent filename. Not a physical firmware request.

V16 adds firmware-events.sh before WIFI_DRIVERS. Start standard mdev -df -vv,
reject nonempty/symlinked command config or existing PID file, require alive
owned child and protocol15/group1 socket in /proc/net/netlink. Save mdev.log
and firmware-events-ready in RAM. Firmware/module/kernel/keys and V15 station
guard/timing unchanged. Native exact service+netlink/duplicate/config refusal
and firmware transfer1792088320210496041 PASSED; exact resetguard
1792088320433247704 PASSED. Independent wifi-v16-image-validation PASSED.
CandidateSHA73311e9613a002a5bf3d3d4c4b5057840b7a427a06e1aff18a186e27e68614f6,
ramdisk1648368/gzip12244544. No extra stock firmware guesses or custom loaders.
BusyBox reference source reviewed upstream mirror/master; it is a reference,
while tests exercise our exact binary. Do not assert root cause proved yet.

Synchronized runner session24969 started; collector
logs/wifi-v16-contact-1792088458962783571/result.json. Inspect runner output for
exact trial receipt/accepted write before assuming installed image. Onlyboot_a
authorized; no extra handset commands while passive observer active. On SSH
proof+ack retain Linux; otherwise returnedFastboot freshACL/LK/stockundo.

### V16 returned early payload failure; stock restored; V17 prepared, UNFLASHED

Trial1792088460069768892 returned256.613597692s, code23, residual0.219903618s:
bootstrap154/read-own-payload failure; Wi-Fi service therefore not yet physically
proved. Preserve timing interpretation limits. LK1792088900885362409 succeeded,
NONRST_REG2=0x28002003/wdtstatus0x2. Stock undo1792088922188623103 send/write
accepted exit0/no reboot. LAST INSTALLED BOOT_A STOCK; USB001/010. No active
phone collector/observer. Additional exact V16 real-loop/vendor extraction test
1792088902300641153 PASSED, does not reproduce physical failure. Compressed
payload12244544/expanded30448640 with /run128MiB; no identified RAM-size shortage.

V17 prepared to capture10 own-payload phases and retain unchanged V16 radio/
firmware service. Init adds only RAM phase file; no partition writes. Decoder
expanded to50slots, 80+5*code exceptlate9=525, same3s margin guard and660observer.
Bootstrap154 with phase1..10 maps40..49, unknownphase remains23. This diagnoses
discovery/node/size/RO/metadata/read/hash/gzip/cpio/final-log separately in one
boot. CandidateSHAe24e21797997312ec21bae8f07256a3cf17411462ac6c30518543fbb2677dcab,
ramdisk1648523. UNFLASHED; native phase/fault/timing and independent validation
required before trial. Payload/module/firmware bytes unchanged from V16.

### V17 validation PASSED; trial ACTIVE

Batched native49timing resets including late-slot/refusal passed1792089294576390735.
Real loop/vendor payload read/extract plus10fault-phase injections passed
1792089295277420728. Exact image resetguard passed1792089294836530621.
Independent wifi-v17-image-validation PASSED with350decoder boundary cases.
Marker steps distinguish payload operations without changing their behavior.
Same V16 firmware daemon still awaiting physical proof. Station guard unchanged.
Collector logs/wifi-v17-contact-1792089398405100243/result.json active.
Trial logs/boot-a-wifi-v17-trial-1792089399288442769.json; runner session67652.
Inspect receipt for accepted boot_a write/reboot; no commands while observer.
On pinned nativeSSH+ack keep Linux and gather full logs; otherwise returned
Fastboot freshACL/LK/verifiedstockundo(no reboot). Decoder is now
tools/lynx_payload_fast_timing.py (50slots,80+5*code exceptlate9=525).

### V17 reaches actual Wi-Fi interface-up and WPA start; stock restored

Trial1792089399288442769 returned166.895728017s, code13, residual0.062226707s:
worker143/WPA association deadline. On exact source path payload/storage/
calibration, stock clock/module startup, firmware daemon, chip check, station
command, netdev discovery, ip-link-up and wpa_supplicant startup all succeeded
first. Does not prove scanning, authentication, DHCP or SSH. No UDP/nativeSSH.
V16 early payload failure not reproduced here; V17 payload markers were not
needed on this boot. Standard firmware service now has startup-path evidence,
not independent capture of each physical firmware transaction.
LK1792089735394606412 succeeded; NONRST_REG2=0x28002003/wdtstatus0x2.
Stock restore1792089744635556434 accepted send/write OKAY exit0/no reboot.
LAST INSTALLED BOOT_A STOCK; USB001/011. No active phone collector/observer.
V17 candidate preserved as most advanced hardware-tested Linux image.

Read-only active profile audit1792089829386746311: host profile Noobia MT7612U,
SSID Noobia, key_mgmt wpa-psk; embedded PSK cryptographically matches (key never
logged). Cached AP Noobia channel6/2437MHz/WPA2; not hidden. Embedded countryBG,
protoRSN, ctrl_interface=/run/wpa_supplicant matches polling path. No credential
request needed. Next gather current WPA status, cached scan list, rfkill and
supplicant messages in one trial; classify current boot without key exposure.

### V18 WPA diagnostic candidate prepared, UNFLASHED

CandidateSHA62bfed751f3793f63132d2ca3181a5aa869f4f5ce6efcb640abbcaecc9ba4f40,
ramdisk1648722/gzip12245495. Add wpa-diagnostics.sh/public targetSSID, bounded
3s status+3s cached scan queries, read-only rfkill snapshot, -d supplicant log
(no -K/show-keys). Bind snapshot to current token. If final status is COMPLETED,
continue DHCP; otherwise report status/scan/key-error/rejection/rfkill/category.
No credential changes, forced scans or radio state writes. Kernel/module/stock
firmware/clock/daemon/station flow unchanged; keep V17 best tested image.
New60-slot prioritized grid: WPA50..59=160..205s, payload40..49=210..255s,
stack25..39=260..330s, generic0..24=335+5*code, late9=525; same3s margin guard.
Observer660s. Association diagnostics target about3min; early stage regressions
may take longer. UNFLASHED: tests/independent validation pending.

### V18 validated; association diagnostic trial ACTIVE

Host+actual ARM BusyBox24 WPA parser/snapshot cases passed1792090425998148659.
Native58timing resets +late/refusal guards passed1792090547899679543;
actual block/vendor extraction passed1792090550012668570; exact resetguard
passed1792090550350855812. Independent wifi-v18-image-validation PASSED with
420decoder boundary cases. Reuse pinned unchanged parent/module/credential
checks rather than recursive retesting. TargetSSID/key unchanged and verified
against active host Noobia profile. No firmware/module/radio state changes.
Collector logs/wifi-v18-contact-1792090708114511204/result.json active;
runner session86852. Inspect output for exact trial receipt and accepted write.
Priority WPA codes50..59 at160..205seconds (+calibrated reboot baseline),
decoder tools/lynx_wpa_timing.py. Observe without extra handsetcommands;
on SSHproof+ack keep Linux; otherwise returnedFastboot freshACL/LK/stockundo.

### V18 complete; stock restored; WPA launch root cause reproduced locally

Trial1792090709237264802 returned181.733827879s: code50/control-status
unavailable, residual0.099673431s. No nativeSSH or UDP proof. LK capture
1792091551672357246 returned0; NONRST_REG2=0x28002003. Verified stock boot_a
restore1792091559039878148 accepted send/write OKAY exit0, NO reboot.
LAST INSTALLED BOOT_A STOCK; USB001/012. Other partitions unchanged.

Exact WPA binaries dynamically linked: initial local fixture omitted loader/
libraries (preserved1792091616234535443); corrected fixture included exact
supplement libraries1792091646205899235. Actual wpa_supplicant2.11 does NOT
support -f: original command prints usage and exits0 WITHOUT a daemon even
with wired loopback. This invalidates earlier inference that -B exit0 proved
daemon startup or that code13 proved association failure. Interface discovery
and ip-link-up evidence remain valid. Remove -f: actual server/client PONG and
wpa_state reply succeeded1792091691955569851 under exact stock ARM kernel.

V19 replaces -B/-f launch with owned foreground daemon backgrounded by shell,
stdout/stderr privateRAM log, PID tracking and bounded socket+PONG readiness.
Exact launcher tested1792091882279471372: livePONG/status, logcapture and
invaliddriverrefusal all passed in8.63s; no NIC or real credentials. Actual
block/vendor payload1792091878654321570 passed. Kernel, firmware, modules,
credentials, bootstrap, reset guards and timing unchanged (reuse pinned V18
receipts rather than rerun identical code). CandidateSHA
5ce2dbf8a7c132fa7e31f6be70aa76f83afe8c293e2cd5f02251a532486fd851;
ramdisk1648718, supplement12245792. V19 currently UNFLASHED; independent
validation in progress. User requests faster batched tests; local pair checks
take about9s and payloadcheck ran concurrently. No physical action needed.

### V19 validation passed; hardware trial ACTIVE

Independent docs/wifi-v19-image-validation.json PASSED. Validator's initial
unsupportedflag check also matched explanatory comment; narrowed to command
argument bytes, candidate/source unchanged. Fresh collector
logs/wifi-v19-contact-1792091967236871487/result.json; trial
logs/boot-a-wifi-v19-trial-1792091968352709663.json. boot_a send/write accepted,
one reboot accepted. Runner session29916 active; passive observation660s.
CURRENT INSTALLED BOOT_A V19. No additional phonecommands during observer.
If no pinned nativeSSH+cancelack: freshACL/read-onlyLK, restoreverifiedstock
boot_a withoutreboot, then inspect current-token timing category. Do not treat
original WPA -B exit0 as evidence of a live daemon (rootcause recorded above).

### SUCCESS: native Wi-Fi, DHCP and pinned SSH verified on Lynx

V19 trial1792091968352709663 succeeded. Contactreceipt
logs/wifi-v19-contact-1792091967236871487/result.json state native-ssh-available:
phone192.168.100.9; pinned hostkey/exactkernel/PID1BusyBox/initSHA/BusyBoxSHA/
currenttoken/rootUID all matched. Tokenack exit0 cancelled automaticfallback.
Collector received beacon after108.94s; logs show WPAstart85.14s,
associationwait86.14s,DHCP87.15s,SSHready91.13s. No Fastbootreturn needed.
Decoded/retrieved journals valid: supervisor2,bootstrap84,wifi105records.
CURRENT BOOT_A V19; RUNNING NATIVE LINUX; DO NOT restore stock on this success.
Runner29916 finishedexit0; no observer/collector remains running.

Independent capture1792092117801695142 proof+health+dmesg succeeded. Broad
tar of all /run/lynx included bulky payloaddata and timedout35s after32.7MB;
partialarchive preserved. Narrowed to bounded runtime records; new capture
1792092186336551640 allcommands exit0 in2.21s, archive282917bytes validated
44members. Health confirms wlan0 UP192.168.100.9/24, routevia192.168.100.1,
WPA2-PSK/Noobia/stateCOMPLETED. Full kernel log saved827344bytes. Real phone
logs now available, no longer limited to timed reset inference.

Working artifacts preserved under busybox-wifi-ssh-twostage-v19. BEST-LINUX-BOOT
updated to actual authenticated hardware milestone. Connection helper
tools/lynx-ssh (invoke via bash), capturetool tools/capture_lynx_live.py.
Procedure docs/NATIVE-WIFI-SSH.md includes exact stock undo and requirement
to start V19 collector before future reboots: fallback cancellation isRAMonly.
Logs and runtime rootfs remain RAM onphone; archivedlocally before anyreboot.
No further flash/reboot needed. No GUI/fullpostmarketOS installation yet.

### Publication and thermal safety hold

Published scoped source/docs/tools commit d304dcb on GitHub branch
lynx/native-linux-wifi-ssh. Exact recipe rebuilt V19 byte-for-byte from private
objects and stock boot, no earlier experimental image needed. Private cache
checkpoints/native-wifi-ssh-v19 contains137deduplicated inputs and both boot
images; never upload it. Publication audit812files/4262699bytes passed.

Later SSH remained reachable after about100min. Read-only live inventory
1792098110330311623 found ext4/f2fs/erofs support, complete UFS partition
metadata, userdata sdc85 (466026432sectors), boot_a sdc39 readonly1. All other
partitions unchanged/unmounted. No storage writes or new modules.

Noob then reported heating and explicitly prioritized battery safety. Immediate
read-only heat check at6219s: battery supply/temp absent; only MT6375 charger
Notcharging/online0/typeUnknown;42of43thermaltemps EINVAL, consys33000only;
no CPUfreqpolicies or coolingdevices; top99–100%idle. Cannot verify thermal
protection or infer battery temperature from consys. No subsequent phonecommand
needed; asked Noob to unplug USB and power off to cool. Power-off NOT confirmed.
Hardware development paused; offline investigation only. THERMAL-SAFETY.md and
active SAFETY-HOLD.json record this. V19flash action now refuses before phone
access; stockrestore remains allowed. Never silently clear hold or treat V19
as a thermally validated unattended image. All successfulboot artifacts intact.

Noob subsequently CONFIRMED unplugged and shut down. No further phone commands.
V19 thermal hold refusal tested: --flash-linux --reboot exits with expected
safety exception before validation/USB/network access. Work continues offline.

Offline module audit1792098400716154704: absent mediatek-cpufreq-hw,
soc_temp_lvts,thermal_interface,thermal-generic-adc,mt6375-battery,oplus_chg,
tcpc_mt6375; dependency closures miss2/1/11/1/9/8/1respectively. All resolve
to matching stockfiles. First audit1792098391447688670 normalized index but
not dependency references; fixed normalization and preserved both reports.
Frameworks CPUfreq/thermal builtin; keyhardware drivers modular. PSCIidle
builtin does not establish actual lowpowerstate. Cause of heat not proved;
no driver loaded and no new bootimage built/flashed after safety report.

### Thermal modules prepared for manual stages AFTER Wi-Fi/SSH

Noob requested Wi-Fi first to preserve diagnostic access. Chose RAM-only SSH
pack instead of modifying boot_a; no new image or startupsequence change.
tools/prepare_thermal_pack.py produced thermal-ssh-pack-1792098954724495751:
2291277bytes/43matchingstockmodules, SHA
e68329332419a9a95dbf6bfe0a632fd983272b1c2eb496294b6c1b57e28f4228.
Exact vermagic/shared importCRC/dependencyorder checks passed, noCRCconflict.
Enabled stockDT matches: /lvts@10315000, performance-controller@0011bc00,
/soc/oplus-omrg. Stage1sensor missing1module; stage2CPUfreq missing2modules.
Other groups (ADC/thermalintegration/battery/charging/TypeC) bundledreviewonly.

thermal-step.sh defaultsreadonly. Pack REVIEW-HOLD blocks liveinsertion;
checksumcovershold so do not simplyremoveit. Live path (future reviewedpack)
requires SSH/currenttokenack/exactkernel/packhashes/DT hashes; CPUstage requires
real soc_maxtemp0<value<50000 (conservativecutoff,NOT batteryguarantee).
Perstagebefore/after snapshots, INSMOD_BEGIN andreturnjournal, noautoload,
noretry/unload, no governor/charger/thermalregisterwrites. Kernelhang can still
loseSSH anddefeat softwaredeadline; hardwaretestnotauthorizedbyofflinechecks.

NativeARMguardcheck emulated-thermal-pack-guards-1792099050555858301 PASSED:
hold/reviewonly/noSSH/token/hash/DT refusals, unchangedloadedmoduleinventory,
cleanpoweroff. Fullpackintegrity andordereddependencies checked. Nophysical
probe attempted. Doc THERMAL-AFTER-SSH.md, Makefilethermal-pack/thermal-check.
PHONE REMAINS OFF. V19unchanged andboththermalholdsactive. Next offline review
probe/clock/regulator sideeffects, then a separatelyreviewedshortsupervisedtest.

### Supervised sensor-only cold trial prepared after Noob confirmed cooldown

User asks continue cooled. Review pinned OnePlus source found missing DT-level
calibrationprovider nvmem_mtk-devinfo.ko, despite no ELFdependency. Add before
LVTS, checkchosenatagcount1..400/fullsize/mincellcoverage before anyinsertion.
Provider registers readonly NVMEM frombootdata; sensorprobe normallyinitializes
hardware andthermalrebootprotection. Exactstockmodulesunmodified. Clock/reset/
project prereqs verifiedpresent inoldinventory andrequiredagainlive. No hand
registerwrites, fuseprogramming, charging or CPUfrequency stage inthistrial.

Sensorpack1792099635423460996 SHAedc011a45072b6c3baa13da4ba73462d7a0e049236719a54fb093fb2da0ebffb,
44modules/2294722bytes. Onlysoc-temperatureplan enabled; globalflashholdactive.
NativeARMguardtest1792099651403112156 passed. Stop timer test1792099829723111225
passed detachedparentexit/powerdown inVM (90→1secondaccelerated). Hostselftest
pack/identity/timerackpolicy passed. docs/SENSOR-TRIAL-REVIEW.md hasdetails.

tools/lynx_sensor_trial.py willlisten beforepowercue. On SSHproof arms independent
90secondpowerofftimer BEFORE normalfallbackack, uploadsRAMpack, snapshots,
sensorstageonly,dmesg, immediatepoweroffrequest. Timernevercancelled. Physical
poweroffunproven; Noobmustsupervise/override ifheat orhang. No flash/newimage.
No GitHub push unless somethingnewworksonhardware. Phoneoff untilpowercue.

### Cold boot started; listener refreshed before contact

Initial listener logs/sensor-trial-1792100173660028633/result.json was ready
before powercue; user subsequently reported Orange State. Original listener
had already spent about206s waiting before this report, with no phonecontact
or operations. Stopped exact owned PID73789 withSIGTERM beforecontact and
started fresh300s listener logs/sensor-trial-1792100424200752360/result.json,
session90561. No further buttons/reboot required. User told Orange State is
expected/unlockedwarning, not Linuxproof. Observe currentlistener through
sensorstage/shutdownrequest; do not flash or run anyparallelphonecommand.

### SUCCESS: sensor-only RAM trial yielded29validthermalzones; stoprequested

Fresh listener1792100424200752360/session90561 reached pinned SSH at
192.168.100.5 (DHCPchangedfrom.9). Allidentitychecks matched. Stop90stimer
armedBEFOREfallbackack, RAMpacktransfer1.79s, sensorstage0.518s exit0.
Only nvmem_mtk_devinfo andsoc_temp_lvts newlyinserted; bothbindasexpected.
Snapshotuptime98.58s: soc_max34917, CPU~26685..35159, GPU24204/24599,
DRAM~25647..26931, consys29000.29of43zonesvalid; remaining14board/PMICzones
unavailable. No batterytemp, CPUfrequency control,chargingchange orflash.
KernelreportsLKinitLVTS, no fakecalibrationwarning. Sensor milestoneverified.

Saved620107byte kernel+sensor capture; summarize_sensor_trial.py verifies raw
hashes/proof/modules/bindings/ordering/unchangedboot andoutputs sanitized
docs/SENSOR-HARDWARE-RESULT.json. InitialstrictUTF8parsefailed onvendorbytes;
correctedtolossydecodeforparsingONLY, rawpreserved. Summarypassed29/43.

Explicit poweroffrequestedabout5.1safterfirstbeacon; SSHcommandtimedout5s.
No furtherphonecommands. Independent90stimer nevercancelled. Physicalpoweroff
NOTYETCONFIRMED; askedNoob viaasyncquestion. Globalflashholdstillactive; no
furtherhardwaretrial untilphysicalstateknown. V19andprivatecheckpointunchanged.
New workingmilestone qualifiesforGitHubsource/docsupload; no rawlogs orOEMpack.

Noob reports blackscreen and believesoff, cannotconfirm. One bounded pinnedSSH
check to lastverifiedlease192.168.100.5 timedout3s, exit255; receipt
logs/shutdown-network-check-1792100671497745275.json. Consistentwithshutdown,
notproof (networkloss/kernelhang stillpossible). No wake/reboot/flash orfurther
phonecommands. Leaveunpluggedandundisturbed; physicalpowerstateunconfirmed.
Sensor milestone uploadedcommit23b6db2; no newpushforstate-onlycheck.

### Continue offline; next supervised CPU stage prepared

User explicitly permits nextpoweronwithUSBunplugged andaskskeepworkinguntil
physicalinteractionneeded. No furthercommands to poweredoff/uncertainphone.
Reviewedstockcpufreq+OMRG references; exactDT8CPUs/3domains4+3+1 verified,
normalstockDVFSenable/policyregistration, schedutilbuiltin. OMRG sourcevariants
defaulttrue/false differ: do notassume; pinupperlimit-onlyDTrule andrefusefloor.

BatteryDT hasDISABLE_MTKBATTERY plus externalBQ28Z610-flagged0x55gauge. OPLUS
probe mayconfigureSOCparameters; do notloadbattery/chargingbundle fortempread.
Savedprimarysources power-management-sources-1792101036780548667; initial
wrongguessedpaths404 preserved1792101001183070625. Existingpathindexes resolved
correctfiles. Publishedsourcesnot independentlyprovenexactOEMbinaryprovenance.

NewCPU pack1792101216718173026 SHA43ef800701f518317780b6c8afe1623740be0f22799822f0e912ff2286aba5de,
44modules/2296156bytes. AfterSSH sensorsfirst, thenCPUguard requires1soc_max
and>=2CPUtempsall0<value<50000; normalnewmodulesoplus_omrg+mediatek_cpufreq_hw.
No governorsettings/chargerwrites/stress/flash. HashDTCPUdomain/OMRGproperties,
checkabsentdown_limit_enable. NativeARMtest1792101259998565584 PASSED6refusals+
10tempguardcases, nomoduleinsertion. Wrapper tools/lynx_cpu_trial.py selftest
passed; sharedcoordinator retains oldsensorpackreceipt-by-hash forrepeatability.
Onlynewprofile changesstageallowlist. Stop90stimer remainsuncancelled; explicit
poweroffafterlogs. docs/CPU-TRIAL-REVIEW.md. NoGithubpush untilnewhardwaremilestone.


### SUCCESS: combined sensor/CPU RAM trial; power-off requested

User powered Lynx on, USB unplugged. Old CPU listener1792101460405082506
had disappeared before phone contact (session36367 unknown; no owned process).
Preserved its no-contact receipt and rearmed1792101714003328176/session13929,
without another physical button sequence. Fresh pinned native SSH proof passed
at DHCP192.168.100.5. Independent90s stop request armed before token ack.
Sensor and CPU stages returned0; new modules nvmem_mtk_devinfo, soc_temp_lvts,
oplus_omrg, mediatek_cpufreq_hw. No battery/charging modules or partition writes.

All three cpufreq policies exposed mtk-cpufreq-hw/schedutil, CPUs4/3/1. Second
sample: policy0=500000, policy4=400000, policy7=3050000kHz. Largest core at max;
do not infer reduced power/heat. Cooling interfaces0/1/2 have max23/29/27,
current0: registration proven, active throttling NOT tested. SoC38574mC,
29 valid sensor zones. OMRG rule disabled. Actual gauge I2C client7-0055,
name bq27541-battery, no bound driver shown. I2C metadata only, no raw transfers.

Explicit poweroff requested6.34s after beacon; SSH command timedout5s. Timer
never cancelled. Physical poweroff NOT confirmed; no further phone commands.
V19 image/checkpoint/stock undo unchanged; global flash hold remains active.
CPU-HARDWARE-RESULT.json generated by summarize_cpu_trial.py verifies capture
hashes, identity, ordering, exact insertion returns, policies/cooling, bindings
and unchanged V19. CPU-TRIAL-RESULT.md preserves repetition and limitations.

Battery review: exact stock CONFIG_I2C_CHARDEV unset; cannot assume /dev/i2c-7.
CONFIG_IKHEADERS=y, MODVERSIONS=y, full clang LTO and strict CFI enabled.
Published kernel Makefile is also5.10.149, but exact binary ABI still needs
verification. Embedded header extraction investigated OFFLINE, no handset
contact. First extraction refused OEM symlinks; preserve failed receipt
stock-embedded-headers-1792102434815984914. Revised extractor inventories links
without following/extracting them. Need matching compiler and symbol versions;
headers alone do not make a loadable diagnostic module.


Embedded-header extraction SUCCESS, entirely offline: archive at Image offset
27525811,3774320bytes,SHAa4d9e0f432ccc34a4b2a71f3f952354172e18ce0e5de2bde6719bc9f60a383f8,
8739regularheaders/sixsymlinks notfollowed. Exactrelease matchesV19. Receipt
artifacts/stock-embedded-headers-1792102559855818099/result.json. Kernelcontains
another invalidXZmagic candidate, recorded. No unpack/build/load/handsetcontact.
Audit522stockmodules found no conflicts for observed I2C/module-layout imports;
receipt artifacts/gauge-reader-prerequisites-1792102617787527051/result.json.
Pinned gaugeheader confirms familytemp0x06 vsBQ27411temp0x02; TIprimaryTRM
SLUUA65Esection12.1.4 confirmsBQ28Z610readword0x06temperature0.1Ksealedaccess.
Actualchipstillnotidentified; no rawI2Ctransferperformed. Missing matching
Androidclang12.0.5/r416183b andproperCFIKbuild environment; nothardware-ready.
BATTERY-READER-PREPARATION.md preserves findings/nextbuildrequirements.

Offline CPU summary and coordinator self-test passed. Publication audit
1792102663710714658 passed838files/4374024bytes, no secret/privatepathissues.
No furtherphoneoperation afterpoweroffrequest. Before anynextsupervisedboot,
confirmphysicaloff/coolstatus; currentdisplay/networkstateunknown.


### Black display after CPU trial: one bounded reachability check

Noob reports black screen, uncertain power state. Explained native V19 also
has no display, so this is not power-off evidence. Reusable read-only helper
check_shutdown_reachability.py targets the last pinned-identity CPU receipt,
never scans/wakes/acks/reboots/loads. One SSH proof attempt to192.168.100.5
returned255 after~3s, no native proof. Saved raw streams and hashes in
logs/shutdown-reachability-1792103000932384332/result.json. Physical poweroff
stillunconfirmed: could be off, changed lease, lostWiFi orhungkernel. No further
phone operations. KeepUSBunplugged; askNoobwhethercool orwarm withoutbuttons.
No GitHub upload for this state-only observation.


### Continue on Noob's cool/unplugged confirmation; raw gauge module prepared

Noob confirmed Lynx cool and instructed continue, USB unplugged. Accept this
physical status; no repeated power-state confirmation loop. Offline work only
so far. ExactGoogleAndroid7284624clang12.0.5/r416183b downloaded/identityverified,
446466096bytes; tools/gauge-build-inputs-1792103708378707350. Pinned sparse
Kbuild/API source checkout succeeded (81ec42a), so stopped exactowned slow full
kernel downloader PID withSIGTERM; partial+receiptpreserved. No otherprocess
orphoneaffected. Bootstrap defaults compiler-only now; no global installations.

New one-shot lynx-gauge-sample.c defaults refusal; explicitenable requires
exactDTpath/BQproperty/compatible/adapter7/address55. Only SMBusreadword0x06,
cache rawword, no datawrite/config/calibration/charging/scan/retry/autoload.
Modelunverified; not registered as batterytemp or used for safety decisions.
SourceSHA c646f5c5897d3dcced770ec3c3c981ce2a59bff61ab7d1b913acf1ba54ed37c4.

Logic mockedCtest passed1792103944676969260 (firststubcompileerrorpreserved
1792103868286040388). Isolated Kbuildbasis usesunmodifiedsource+exactheaders,
no configregeneration/kernelrebuild. Genuine OEMimportCRCs pairedwithverified
sourceexportdeclarations; partialtable107symbols, no guessed/forcedversions.
Firstbasis1792104422448881745 failedmacroexpanded_dev_info/_dev_err exports;
macrochecked explicitly thennewbasis1792104554981554338. StaticCFIsectioncheck
initiallyfailed althoughsymbolsvalid; archivedattempt beforecorrectedsymbol
check. No CFI/LTOdisabled. SuccessfulmoduleSHA
9b40f97120dc87329ef42aa74742dca51ddb56f40e78dcfa6df7b7c37662e374.

Actualmodule stockARMkernelVM1792104678354338978 PASSEDdefaultrefusal,
explicitregister, unload, cleanpoweroff/noCFIfailure. NoI2Cgauge/probe inVM.
Remotecommand fixture1792104959339213259 PASSED6cases inclrawread+unload,
boundclient/badmodule/hotguard/deadtimer/readerror. Early command composition
mistakecaughtbyinspection/correctedbeforefixtureexecution; syntax-onlychecks
wouldnotcatchit. No physicalmoduleloadyet.

Separate lynx_gauge_trial.py pinsallreceipts/source/module/commandhashes;
reusesfrozenCPU pack exactly; optionalafterCPUhook insharedcoordinator defaults
None foroldprofiles. Sensor/CPU/gaugeselftestallpass. Stop90s remainsarmed before
ack; freshCPUguard+unboundclient+modulehashchecks beforeone-shotread/unload;
logs/snapshots/powerofffollow. V19/stockundo/flashhold unchanged. New detached
bounded start_gauge_listener.py verifiesactualreadiness/PID beforepowercue,
to avoidoldsessionloss. No GitHubpushuntilnewhardwaremilestone.


### SUCCESS: custom gauge read on real Lynx; raw2937; unloaded and stoprequested

Detached listener launch1792105072103874650 PID92629, actualreadyreceipt
logs/gauge-trial-1792105072191821745/result.json. User saidokgo afterpowercue.
Listenerremainedalive acrossuserturn; contact at~119s. Brief40sobserverwindow
ended beforecontact; nextsavedreceipt alreadycontainedfullsuccessfultrial.
No secondbuttons/reboot. Pinnednativeproofmatched. Sensor/CPUstagesreturned0,
freshCPUguardmax34891mC/12samples. Newmodule uploadedhashverified, actualprobe
returned0 in1546us; cachedsysfsword2937 matchedkernelLYNX_GAUGE_RAWword2937.
Readonefixed0x06word, moduleunloaded0. No CFIerrors observed; noconfig/auth/
chargingwrites, no partition changes. Thisproves realcustomnativekernelcode
plusI2Cread, notyetexactgaugemodel orcalibratedbatterytemp. Expectedstockunits
wouldyield20.6C; keepconditional. summarize_gauge_trial.py verifiedallstream
hashes, identity/order/timer/stages/wordmatch/unload; analysis.jsonbesideraw.

Stop90stimer armedbeforeack. Explicitpoweroffrequested6.868safterbeacon;
SSHtimedout5s. Physicaloffunconfirmed; nofurtherphonecommands. Useralready
confirmedcool/USBunplugged beforetrial; do notresumephysicalconfirmationloop.
GAUGE-RAW-RESULT.md preservesmilestone; newworkinghardware qualifiesforone
GitHubupload. Nextofflinework: documentednormalDeviceTypequery, notunsealing
orfullchargingdriverload. V19image/undo/checkpoint/slots unchanged; holdactive.


### Raw milestone uploaded; next DeviceType query prepared offline

Rawreader source/tests/sanitizedfindings pushedaaa2549 onexistingLynxbranch.
No images/rawlogs/compiler/secrets published; audit1792105528880448630 passed.
No newphoneoperationafterfirstgaugepoweroffrequest. Offlinepreparedseparate
lynx-gauge-identity.c: exactOEMDeviceType selector0x0001writewordtocontrol0x00,
msleep20, readword0x00, cache raw_device_type. Fixedclientguards/defaultrefusal,
no retries/othercommands. TIreferenceMACData convention differsfromOEMcontrol
reply; recordactualresponse, comparestockheaderfamilyconstants, do notguess.

SourceSHA92289b3be59b6ed71d7862e280874e87f54d16a9afb0c1634550e1bed33465d4,
moduleSHA93f4fc1e15ece375dfabdedff9dd460fc513a752845f1e902dd08d8248b06df6.
Newisolatedbasis1792105646594458259; pinned sparsecheckout addedkernel/time/timer.c
forgenuinemsleepexportdeclaration. Build/stockCRC/fullCFI/LTOpassed. ActualC
logic1792105646466821751 passed inclfixedquerywhitelist/writeerrornoread.
StockARMVM1792105712214035956 passedrefusal/register/unload/cleanpoweroff;
no gaugeprobe inVM. Hostcommandfixture1792105758653461063 passed6cases;
firstfixture1792105745459818986 caughtoldmodulehash, preservedandcorrected.

Newwrapper lynx_gauge_identity_trial.py pinsallnewreceipts; rawprofilepreserved.
Sharedvalidator generalizedSOURCEpath only; nativeVM andcommandtests have
explicitidentityflags. Allthreeprofiles identity/raw/CPUselftestpassed, andold
rawhardwareanalysisstillverifies. summarizer --identity-query willrecordrawid
andrecognizedstockfamilywithoutclaimingcalibratedbatterytemp. Newlistener
launcher --identity-query retainsreadiness/PIDverification. GAUGE-IDENTITY-TRIAL.md
preservesreview. NoGithubpushforprepared-onlyidentitycode. Nextactionarmbounded
listener thenpowercue; USBstaysunplugged. Nootherphysicalconfirmationrequested.


### USER REVOKED unconditional shutdown; continuous battery session authorized

Noob explicitly requested keep Lynx running while possible, develop overSSH,
and focus battery. This supersedes earlier90s/end-of-test shutdown policy for
this USB-unplugged session. Stopped owned oldlistenerPID96226 beforecontact;
receipt1792105856006154847 hadno phonecontact/timerarmed. No phonecommandissued.

Sharedcoordinator now has --keep-running: upload/arm thermal-watch.sh BEFORE
fallbackack; no elapsedtime shutdown and no finallypoweroff. After sensorstage
activatewatch, thenCPU+gaugeidentityquery/logcapture and leaveSSHrunning. Old
shorttrialmode preserved for historicalrepeat, but userrequestedcontinuousmode
is selected now. Watch samplesSoC/CPUevery5s, temperature-triggeredpoweroffonly
at>=60000mC; missing/invalid readings logged asunknown, not cool. No batterytemp
safetyproof fromthis CPU-onlywatch. Doesnotchangecharging/thermaltripregisters.

Watcher real-shellfixtures1792106083956166481 PASSED9cases; actualpoweroffmocked.
SourceSHAdacb8380a8210db439e6abc30d16477e727bea40fb9f3c2798601850ae4c0c35.
Continuousidentitycommandfixtures1792106084010347755 PASSED6cases; commandchecks
thermal-watch.pid ratherthanoldtimerpid. Profile--self-test--keep-running passed.

NewdetachedcontinuouslistenerPID97175 actualready:
logs/gauge-listener-launch-1792106150629481131/result.json
trialreceipt logs/gauge-identity-trial-1792106150717277643/result.json
--identity-query --keep-running --seconds600. No contactyetatlaunch. Nextneed
poweronifoff, USBunplugged. Oncecontactinspectreceipt and keepworkingoverSSH,
doNOTrequestshutdownforroutinecapture/end-of-test. PreserveV19/boot_a/stockundo/
recovery/slotB; Linuxflashholdremainsactive, runtimecontinuouspermissionexplicit.
NoGithubpush forprepared-onlychanges untilnewhardwaremilestone.


### User reconnected Fastboot; reboot blocked by host USB permissions

After user-reported manualrestart intoFastboot, oldhostloggerPID105324 stopped,
109savedsamplespreserved (lastSSHrc0). Nothing onphonewaschangedbythestop.
BatteryhardwareworkBEFORErestart succeeded: ZY0603id0xa5ff, customread-only
monitor moduleSHA10df9e698e020893e9d28796db8bd1a93ffdd6c2d9779463f678a3687f0c931d,
sourceSHA24a3c1e82221c70ad0d0bdf17e92ab046f57e4bdd3cf6ff0e40c8e3a5a0b25f8.
Successfulbasis1792107325426159905, Clogic1792107325293433508,
stockARMVM1792107583177053380; actualinstallreceipt
logs/battery-monitor-install-1792107625689113056/result.json.
Initialactualsnapshot26.4C/96percent/8595mVpack/-282mAgaugesigned; all4errors0.
Batterywatchtested1792107472499668309, SHA4c575f30a530821cbc3fc9f4aa0cce0bfb5a1d44eebd60f95f7b5cf2cdc8520e;
startedlive1792107672666653598, samples5s, cutoff45CbatteryONLY, noelapsedstop.
CPUwatch60Cunchanged. Hostcollectorlogs/battery-session-1792107674189909873.

Read-onlyidlediagnostics: psci_idle/menu available, CPU0WFIusageonly, deepstates
zero observed; iw powersaveoff. No idle/WiFi power settings were changed.
PinnedWiFipowersourcefetch artifacts/wifi-power-source-review-* hadbeenstarted;
inspectreceipt/sourcebeforeanyfuturepowersavetoggle. Nocharge/calibrationwrites.
Several failedmonitorbasis/auditattempts retained; finalbuildusesunsignedint
param_ops_uint with genuineCRC, explicitlycheckedSTANDARD_PARAM_DEF exportmacro.

Newresume_battery_session.py automatesexistingV19RAMsetup: identityquery+
sensors/CPUcontinuoussession, analyzeZY0603reply, verifiedbattery-monitorinstall,
watchstart andhostlogger. NEVERflash/reboot/shutdownbyitself. Newwaitingworker
logs/battery-resume-1792171173913624900/result.json PID14496, listenertrial
logs/gauge-identity-trial-1792171174067380049/result.json,600sdeadline.
USBnow0e8d:201c atbus001/device005, fastbootreportsno permissions. sudo-ngetvar
failedpasswordrequired; no reboot/getvarpacket/flashissued. Read-onlyattempt
logs/resume-fastboot-check-1792171198723239188.json. Needhumanhostpermission
forcurrentUSBnode (temporaryACLaria:rw), thenverifyserial89BYAY5L4T9HFUOV,
productk6983v1_64/unlockedyes/slota/bootloaderk6983v1_64_45ca337_202308100614,
ensurelistenerstillready,andfastbootrebootONLY. ImmediatelytellNoobunplugUSB.
AllRAMtoolswerelostbyuserrestart; V19boot_aunchanged. NoGitpushyetforbattery
monitor milestone; latestpushedaaa2549rawreader. Preserve/audit/publishnewworking
batteryproofonceconnected,withoutprivateassets/rawlogs/credentials.


### Repeat boot SUCCESS: automatic battery resume and continuous SSH restored

User grantedUSBACL; fastbootserial89BYAY5L4T9HFUOV visible. Fixedread-only
preflight1792171508710722121 passedproduct/unlocked/slota/stockbootloader,
slot-successfulyes/unbootableno/retry7, sizesunchanged. Listener/workeractual
heartbeatverifiedand>160sremain beforefastbootrebootONLY. Rebootreceipt
logs/resume-fastboot-reboot-1792171546511770322.json exit0; noflash/slotchange.
ImmediatelytoldNoobunplugUSB; userreportedOrangeState, expectedunlockedwarning.

Listener reachedpinnednativeSSHandidentifiedZY0603again; newDHCP192.168.100.9
(previous.5). Automatedworker logs/battery-resume-1792171173913624900/result.json
stateonline, allsteps0. Sessiongauge-identity-trial-1792171174067380049.
Monitorinstall1792171660594161155 passedexactsource/module/VM/Cfixtures,
firstsnapshot22.1C/91percent/8440mVpack/-265mAgaugesigned/allerrors0.
CPUstageguardmax39696mC. No old90stimer/end-of-testshutdown, CPUwatch60C and
batterywatch45Cconditionalonly. Hostloggerbattery-session-1792171663995277546
statewatching, one-hourboundedhostcapture; phonewatchers/SSHremainongoingafter
loggerends. Fullresumedkernel/watch/batteryproof savedlive-resumed-battery-proof-
1792171777720519037. summarize_battery_monitor.py verifiesstreamsandwrites
sanitizedBATTERY-HARDWARE-RESULT.json. Noexternaltempcalibration/fullthermalclaim.

Fixedlynx-sshhelper toresolve newestverifiedcontinuoussessionaddress dynamically,
strictpinnedkey/key-onlyauthunchanged. Wrappermadeexecutable; actualtestuname+
battery-last passed, latest23.0C/90percent/-151mA. Do not hardcodeold.5lease.
README/BATTERY-MONITOR.md/currentmetadata updated; runtimecontinuousauthorization
supersedesoldextendedrunhold, Linux-flashholdstillactive. V19imageunchanged.

WiFipowerreview sourceatartifacts/wifi-power-source-review-1792107802822693331
showedcfg80211enabled/timeout-1 mapsFAST_PSP, disabledmapsCAM; TIMcheckfailsclosed.
CPU0deepidlestatesdisable0buthadzeroentries, onlyWFIused; noidleconfigwrites.
Reversible30sWiFiPStrial1792171973859561016: originaloff, onverified, sixliveSSH
samples, independentrollbackreturned0/off. Battery23.4..23.5C/90percent,
gaugecurrentoscillated~127..259mAdischarge. Shorttrialprovesconnectivity/support,
NOTquantifiedpowerreduction. ReenablednormalWiFiPSforthisRAMsessionwithseparate
pinnedlivecommand; noautomaticboot/persistentimagechange. Nochargerwrites.
Newworkingbattery+repeatbootmilestonequalifiesGitHubupload; runpublicationaudit
beforestagingonlylynx. Rawlogs/OEM/compiler/privateinputsneverpublish.

### CPU idle rejection loop identified; session-only WFI fallback verified

Read-only full-CPU capture added the previously omitted `rejected` counters.
Baseline receipt `logs/live-idle-paired-observation-1792172753457126879`:
12,943,805 rejected entries / 30.42 seconds, successful deep entries zero.
Global CPU latency limit 2,000,000,000us (default), no userspace latency fd
holders. Per-CPU sysfs latency 0 means no userspace constraint, not an effective
0us limit. Kernel source confirms rejection is a negative idle-entry return;
exact rejecting callback/firmware reason remains unknown.

Bounded WFI trial `live-wfi-fallback-trial-1792172856667668114` preserved all
disable flags, kept WFI enabled, disabled only deeper states, and armed an
independent 45s rollback. Three ~10s intervals: zero rejections, SSH continuous,
current -128 before / -102,-62,-64mA during. Normal restore plus detached restore
completed. `live-wfi-rollback-check-1792172907224246832` verified all original
flags restored; current -130mA again. Do not rerun that same-boot trial directory.

Applied `linux-port/wfi-fallback.sh --apply` with separate live receipt
`live-enable-wfi-fallback-1792172983731470335`. Active ONLY in current RAM session;
original flags saved `/run/lynx/wfi-fallback/original-flags`. Undo is pinned SSH
`sh /run/lynx/wfi-fallback.sh --restore`; reboot also clears it. No shutdown timer.
Not automatically applied by resume_battery_session.py and not baked into V19.
Follow-up `live-wfi-session-observation-1792172984704283588`: zero rejections
over 30.41s. 23 later host samples over225s: median -62mA, range -79..-59mA;
66 earlier PS-on samples over676s: median -130.5mA. Unmatched windows/observer
activity mean these are observed distributions, not calibrated idle power or
battery-life estimates. Summaries saved beside the observation receipts.

Final proof `live-wfi-battery-confirmation-1792173245383940426`: pinned native
SSH exit0, battery24.0C/88percent/-86mA sample/allfield-errors0, WiFi power saveON,
both watchers alive, recent valid13 CPU/soc samples max~28.1C. All WFI states
enabled, deeper states disabled. USB remains unplugged; no physical action needed.
Host logger `battery-session-1792171663995277546` continues its original1hr bound;
its end never stops Lynx or the RAM watchers. No flash/slot/recovery writes.

Offline source review saved ten excerpts plus exact commit/hashes and module
metadata at `artifacts/idle-power-source-review-1792173148909952121`.
Stock low-power modules exist but are not resident: mtk-lpm, dbg-common-v1,
plat-v1. Platform initialization includes SRAM writes, CPU hotplug hooks,
suspend registration and VALIDATE_PWR_STATE_CTRL secure-firmware call. Missing
initialization is a candidate cause, not proved. Core/platform module exits
are empty; unloading must not be assumed to undo callbacks. No LPM module loaded.
Keep WFI fallback while reviewing full init/dependencies before an invasive test.

New durable tools: idle-observation.sh, bounded wfi-fallback-trial.sh,
session wfi-fallback.sh, hash-verifying summarize_idle_observation.py and
summarize_battery_window.py. Counter time updates on exit; transition intervals
can include long sleep spanning a capture boundary, so ratios can exceed1.
Do not misreport these as instantaneous utilization. See IDLE-POWER.md.

### Read-only charger status and bounded CPU cooling actuation

`logs/live-thermal-policy-survey-1792173365809276850`: charger online0,
statusNotcharging, battery23.7C/87percent/-71mA. CPUzone step_wise enabled but
no exposed passive trips/cdev bindings; soc_max only116500mC criticaltrip.
Do not infer automatic passive throttling from registered cooling devices.

`logs/live-cooling-control-trial-1792173442046650278`: both watcher PIDs alive,
soc_max<45000mC guard, exact3CPUcooling devices, originals0, max23/29/27.
Detached30srollback armed before increasingeachstate by1 for~11seconds.
Maxfreqs policy0 1800000->1700000, policy4 2850000->2750000,
policy7 3050000->3000000kHz. Stayedlimited10s, allstates/freqlimits restored
exactly, SSHcontinuous, battery23.5C/-58..-60mA, recentCPUmax~27.3C.
No stress/heating/trip/regulator/charger writes, no permanentcoolingcap.
Independentrollback logfile verification follows separately. WFI fallbackON.
New cooling-control-trial.sh and COOLING-CONTROL.md preserve this working test.
Next: implement a small RAM userspace soft-throttle policy, hysteresis,
invalid-sensor handling and concurrent-controller ownership checks; validate
decision logic on simulated readings, never heat hardware just to test it.

### Soft-throttle watcher prepared, tested and running in RAM

Cooling rollback confirmed by live-cooling-rollback-verification-
1792173548004003162, states all0, battery23.3C/-68mA. New source
thermal-cooling-watch.sh SHA5310290b6a8e981e2250910fb5b4b54428a1faa6b1f6177e36f5be2aade1233b.
Host fixtures33 passed artifacts/thermal-cooling-policy-check-1792173709322403443;
samehash actual BusyBox decisionfixtures33 passed live-native-thermal-cooling-
decisions-1792173730554681342. These fixtures never access hardware paths.

Started with pinned source hash, both existing watcher PIDs alive, valid
soc_max+CPU set <40C, exact3cooling devices initiallystate0. Receipt
live-start-thermal-cooling-watch-1792173775271871468: PID25373, READY, first
maximum30316mC/desired0, allstates0, battery23.0C/87percent/-77mA. Ongoing
proof live-soft-throttle-steady-check-1792173851879619153. No artificial heat.

Policy onlyhardware-testedstate1 at>=45C, releaseownedlimits at<=40C,
hysteresisbetween; invalidsensor set HOLD, no relaxinglimit. Externalstronger
state neveroverridden; ownershiploss permanentlycedesdeviceforthisrun.
Best-effort checksnotatomic arbitration. ExistingCPU60C/battery45Cconditional
shutdownwatchersuntouched. No unconditionaltimers. Automatic hot hardware
transition not exercised; manualactuation+actualnative decisionlogic separately
verified. Onexitlastsoftcapretained; explicit--restore onlyafterverifiedownedPID
exits, refuseswhilePIDalive, onlyrestoresownstate1. Noimage/resumeworkerchange.

Updated host collector captures soft-throttlelog too. Replacement logger
battery-session-1792173826897633981 watching3600s, sourcehash inlauncher.
Verifiedhashfirstsample+softlog beforestopping oldexactownedPID15859; gone
confirmed; oldreceiptstate'replaced', replacementlinkpreserved. Rotation
battery-logger-rotation-1792173851845332051.json. Phonewatchers/SSHnotstopped.
Currentloggerenddoesnotstopphone. KeepcurrentUSBunpluggedruntimecontinuous.

### Repeatable RAM power setup and live sleep-prerequisite audit

Lynx remained on the same boot throughout this work; no reboot/flash/slot
change, no driver insertion. Initial live-next-power-preflight-
1792176272086038203: battery22.0C/85percent/-59mA, allthreewatchersalive,
WiFiPSon. Kernel boot ID captured and unchanged during installer checks.

New configure_runtime_power.py pins exact hardware-reviewed WFI source
866c9d2429a10d6cb4294136622668a840d761cfba65037bd95e3cabf290fab0 and
softwatchsource5310290b6a8e981e2250910fb5b4b54428a1faa6b1f6177e36f5be2aade1233b.
Default no contact; --verify-only validates existing complete state; --apply
installs missing RAM scripts/stages or adopts matching live state. Never
overwrites original flags, restarts a dead watcher, clears incomplete markers,
changes charging, requests suspend/reboot, flashes, or arms shutdown timers.
Verifies native identity before/after, matches boot ID, checks watcher command
lines, requires recent error-free battery sample, verifies8CPUWFI+deepflags and
saved inventory. WiFiPS onlyreported, notchanged. Failures preserve useful
already-running stages and evidence; no forced cleanup or poweroff.

Synthetic actual-shell checks11cases+embeddedbytehash verification passed at
artifacts/runtime-power-setup-check-1792178926641896816. Initial failedfixture
1792178126960507552 preserved: sequential mockpath replacement corrupted
/proc/sys; correctedsinglepassmapping. No phonecontactbeforecorrectedtests.
Tests cover check/adopt existing state and refusal paths, not fresh daemon
installation. Live verify-only1792178227391006803 and apply-existing
1792178354915012108 ready; original watcher PIDs17580/18190/25373 retained.
Finalverify1792178927139363263 includes post-operation boot-ID comparison.

resume_battery_session.py --start --runtime-power now optionally runs the RAM
power stage after batterywatch and before logger; flag propagates into worker
and receipts. Default oldresume retained. Full new combinedfreshboot sequence
UNTESTED: do not reboot merely to exercise it while usefulSSHsession exists.
See RUNTIME-POWER.md. CurrentV19 unchanged, globalLinuxflashholdstillactive.

Previous hostlogger battery-session-1792173826897633981 ended normally after
348samples at1hour. Recovered full RAMlogs in live-power-watch-history-
1792178187548078626, snapshot21.8C/83percent/-62mA. Newbounded4hrhostlogger
battery-session-1792178187012953274 watching, allrecentSSHsamples0. Its end
doesnotstopphone/watchers. FullRAMhistories preserved across the host-log gap.

Read-only sleep-prerequisite survey1792178843537269212: no LPM/MCUPM/SSPM/SCMI
modules resident; firmware:scmi stilldeferred; MTKcmdqfoundation resident.
Captured actualkernelFDT445089bytes in live-live-fdt-power-review-
1792178869180168988. New offline audit_live_power_tree.py verifies native/raw
capturehash, parses49selectedpowernodes, resolves25stockmodules across6roots,
checks exactkernelvermagicand sharedimportCRCs(no conflicts), preservesprivate
power-tree-analysis.json. This doesNOTprove safe init or firmware readiness.

Live tree has suspend-method enable, lpm-kernel-suspend0, MCUPM/SSPM reserved
memory, cpupmSRAM, mcusyscontrol and SCMI. Actual driverlinks checked via
live-sleep-driver-binding-check-1792179002427206853: MCUPM,SSPM,SCMI,mtk_lpm
allUNBOUND. Battery21.8C/83percent/-70mA; originalthreewatcherPIDsalive.
Missing initialization is a concrete lead; exact PSCI rejecting path unknown.

Preserved11morevendorfiles at artifacts/lpm-firmware-source-review-
1792178466467282731 plus4bootstrapheaders1792179001805511237; allcommit/hash
recorded. Core replaces idle callbacks, platform clearsSRAM/installshotplug+
suspendhooks and sends firmwarepower-statevalidationSET; itsreturnisignoredby
platforminit. Emptycore/platform exits prevent assuming rmmodundo. Next review
MCUPM/SSPM mailbox+firmwarestartup before a controlledmoduletrial. No rawfirmware
callissued, no lowpowermodule loaded. See LPM-PREREQUISITES.md.

### MCU startup review completed; Alpine ARM64 userspace now runs on Lynx

Same boot throughout; no flash/reboot/slot change/newkernelmodule. Health receipt
live-mcu-review-health-1792179402546118773: battery21.8C/82percent/-66mA,
originalthreewatcherPIDsalive. Preserved11pinnedMCUPM-v2/SSPM-v3sourcefiles in
artifacts/mcu-startup-source-review-1792179403259415815, per-filetimings/hash.
MCUPM remove/exit incomplete; initialization has IPI/mailbox/optional EMI setup,
timesync and worker that canwriteMPAMcachepartitionregs. SSPM init configures
SCMI/sharedmemory/timesync/EMI; probeignoresinternalinitreturn, exitslackcleanup.
sspm_alive sysfsROactuallysends SCMISET. No MCU module or firmwarecallissued.

Reserved-memory-analysis.json inthatreviewdir verifies actualstockmcupm.ko
contains mediatek,reserve-memory-mcupm_share, absentfromactualFDT. Generic
MCUPM-reservednode isnotthatspecificcompatible. Sourceexplicitlysupports
missing sharednode by disablingloggerandcontinuing, so NOTprovedsleepcause.
Memory-regionpropertyisnotwhatthismodulebranchuses; it looksupcompatible.
Deeper-sleepdrivertrialdeferredinexistingusefulSSHsession becauseundoisnot
ordinaryrmmod. ContinuednormalLinuxuserspacefoundation instead.

OfficialAlpine downloads page verified3.24.2 ARM64 mini-rootfs+releaseprimary
fingerprint0482D84022F52DF1C4E7CD43293ACD0907D9495A. Newfetch_alpine_rootfs.py
downloadedHTTPSarchive,sha256,sha512,signature,ncopa.asc into
downloads/alpine-rootfs-3.24.2-1792179591745064903. BothhashesandactualGPGVALIDSIG
passedwithpinnedprimaryfingerprint. ArchiveSHA256
9bf70a7f18ea44094cbb5f70c58f9af129c8214745743db0e68e5502cc2ce773.
alpine_rootfs.py strictlyreadstarinmemory:514nonrootentries/8655157filebytes/
17ARM64ELFs, requiredsymlink/interpreterchecks, parentpathguard, sizecaps.
No hostextraction. Downloadedarchiveandkey/signaturesremainprivateinputs.

Exactstockkernel NIC-freeVM artifacts/emulated-alpine-rootfs-1792179704020333357
passednativechroot shell/musl/APK3.0.8/basepackageprobe+cleanpoweroff. VM didnot
contactphone. Newinstall_alpine_rootfs.py requires verifiedarchive+VMreceipt,
runtimepowerverification,recentbattery/noerrors/<35C/>=20percent, available
RAM>=128MiB, chargeronline0 and /run tmpfs. PinsbootIDeachphase, freshpinned
nativeidentity checks, refusesexistingrootfs/archive. NewfilesonlyRAM.

Firsthardwarepreflight1792179843361874646 refusedBEFOREupload: Pythonconverted
sed backreference into controlchar. Correctedtosimpleawk, addedcontrolchar
rejection, retainedfailedreceipt. Secondtrial
logs/alpine-rootfs-trial-1792179882804930040 SUCCEEDED: verifiedupload/extractto
/run/lynx/alpine-3.24.2, realARM64shell/APKprobe and originalruntimepostcheck.
Actualprobe live-alpine-probe-1792179887811619335 printsstockkernel,
rootUID,musl/busybox/basekeys and LYNX_ALPINE_USERSPACE_PASS. PID1stilloriginal
BusyBox; this isRAMchroot, NOTnewPID1boot or fullpostmarketOSport.

Phoneclockwas1970, DNSexisting, HTTPSrepos/CApresent. New sync_lynx_clock.py
explicitlysetLinuxwalltimefromNexus. live-wall-clock-sync-1792180049910851789
passed epoch1792180049/unchangedbootID/beforeafteruptime. No RTCwrite,
no precisionsyncclaim. WalltimecorrectionkeepsnormalHTTPScertchecksworking.

alpine-diagnostics.sh createdbasicdevnodesONLYinsideRAMrootfs,copiedexisting
resolverconfig, boundedAPKdownload40s, retainedTLS/packageverification,
installedstrace6.19-r1+sixlibs, no services. Nativeproof
live-alpine-package-diagnostics-1792180076545347560: sevenpackagesinstalled,
23total/11.1MiB; realstracechild/bin/true execve/memory/getuid/exit_group0 PASS.
Battery21.9C/82percent afterbriefpackageactivity. No attaches towatchers.

Newtools/lynx-alpine +lynx_alpine.py executeboundedloggedcommands inmatching
verifiedRAMrootfs,currentcontinuoussession+exactbootIDguard, freshnativeproof,
argumentquotingandactualremotereturncode. Helperaddedpublicationallowlist.
Actual apkinfo23packagesand wrapperstracechild/tailexit0 tested. No interactive
terminaladded; eachcommandmax60s. Afterrebootoldrootfsreceiptrefused.

NativeAPKcache fetched9files; cachecapture
live-alpine-diagnostic-apk-cache-1792180285539775454 preservedbinary+hash.
Resolverpickednewzlib1.3.2-r1 butrunningbasehasr0; filteredreplayONLYexactseven
addedpackages, basealreadyprovidesmusl/zlib. Fresh NIC-freeexactkernelVM
1792180385903910645 firstrefusedlocalpackageswithoutcaching(policy99), retained.
Enabledcache-dir/cache-packageswithnetworkdisabledandnormalkeys; VM
1792180457219474992 passed actualoffline7packageinstall+stracechild exit0,
cleanpoweroff. No force-non-repository or signature/TLSbypass.

export_alpine_apk_cache.py matchesVMpassedconsole/hash+sevenAPKhashes fromraw
nativecapture,exportsfilteredtarandverifiesroundtrip. Result
artifacts/alpine-offline-diagnostics-1792180536171444327/result.json; bundleSHA
a1d0bbe5526bda51a176a458fb4cc1111b9289a59534069a04168c990fc22ca1.
Nativeonlineinstall+VMofflinecoldreplay areseparateproofs; fullcombinedfreshboot
hardwareworkflowunexercised. See ALPINE-USERSPACE.md forrepeatcommands/evidence.

Finalruntimepowercheck1792180314504452043 ready, live-alpine-final-runtime-
1792180315544413582 sameboot/PID1BusyBox/walltimecorrect/rootfs16396KiBincluding
cache/battery22.0C/82percent/-60mA/recentCPUmax~27.3C. Fourhourhostlogger
battery-session-1792178187012953274 continues; itsendingneverstopsLynx.
Allnewbinaries/rootfs/APKs/keys/rawlogs remainlocal; publishonlyourtools/docs.
GlobalLinuxflashholdactive, V19/stockundo/checkpointuntouched.

### Alpine direct-PID1 VM, live read-only observability and UFS map

Same handset boot cf5e2ccf-5c49-485e-9403-b12e3d6bb574; no flash, reboot,
slot change, disk mount or kernel module insertion. Initial inventory
logs/live-system-storage-inventory-1792181341591807206: battery22.0C/81percent/
-59mA, allthreewatcherPIDsalive, UFSbound, 86partitions, no disk mounts.

Read-only map logs/live-partition-map-1792181379560943113 records main sdc
255919652864bytes, logical/physical4096, sysfssectors512. Boot_a sdc39 is64MiB;
read-only fullhash matches frozenV19 5ce2dbf8a7c132fa7e31f6be70aa76f83afe8c293e2cd5f02251a532486fd851.
New audit_partition_map.py validates captureproof/hash, geometry/labels/devnums,
bounds/alignment/overlaps and boot hash; offline negativechecks7passed in
logs/partition-map-negative-check-1792181517015425625.json. Sysfs map isnot
independent GPTCRC verification or proof otherpartitionsarevalid.

New test_alpine_pid1_kernel.py boots verifiedAlpine atinitramfsroot inNIC-free,
disk-freeQEMU withsameexactstockkernel. No outerBB/chroot. DynamicAlpine
/bin/sh asPID1 validated $$=1, /proc/1/exe path+signedarchiveELFSHA, manual
proc/sysfs/tmpfsdev+nodes/devpts/run, APKprobe,RAMwrite,CPUvisibility, clean
poweroff. artifacts/emulated-alpine-pid1-1792181417394955482 passedall9checks in
3.97seconds. ThisisVM-only shellPID1proof, NOTnewhandsetboot/OpenRCintegration;
itsinitramfsisnotaflashablephoneimage.

New linux-port/alpine-observability.sh --apply BOOT_ID createsONLYro,nosuid,
nodev,noexec proc/sysfsmounts insideexistingRAMchroot, checksboot/release,
refusessymlinktargets/incompatiblemounts, verifiesoriginaloutermountentries
unchanged. --status makesnochanges; retains partialstateonfailure. Actualapply
logs/live-alpine-readonly-observability-1792181496340538362 passed. Firstprobe
live-alpine-cli-1792181517068390838 stoppedaftergrep expectedouterpathsinside
chroot. Correctedcheckuseschrootrelative/proc,/sys; no mountchange. Nativeprobe
live-alpine-cli-1792181526852271892 passedfree,readonlyflags,Wifistateup,
strace-f childO_RDONLY opens/proc/meminfo and/sys/class/net/wlan0/operstate.
OriginalSSH/Wifi/watchersstilloutsidechroot. Read-onlymountflagsarenota
securityboundaryagainstprivilegedremounts. No devbind/blocknodesadded.

Runtimepowerpostcheck1792181527526386651 ready, mountstatuscapture
1792181528516466130 passed. Bounded4096bytereaduserdata sdc85 in
logs/live-userdata-header-1792181546190048618 foundnoext4/F2FSfirstsuperblock
magic andnotallzero; doesNOTproveencryption,emptiness,orcorruption. No mount/
repair/formatfollowed. Persistentrootfsplacementstillunresolved.
See ALPINE-STARTUP-STORAGE.md forrepeatcommands/limits/evidence.

Codexapprovalsettings separately updated atNoobexplicitrequest andsession
restarted: never/fullaccessactive; sudo-n idverifiedroot. Sudo/confighelpers
andbackupremainprivateunderlogs/permission-setup-1792181177389579893.
ThesehostpermissionsdonotcancelLynxLinuxflashholdor authorizeunrelatedwrites.

### Optional offline Alpine runtime stage and resume integration

No flash/reboot/slot change/driver insertion. Same phone boot and original
PID1 throughout. New linux-port/alpine-runtime-stage.sh is a post-network RAM
stage, not a replacement init: verifies input hashes/boot/kernel, refuses an
existing rootfs for --install, unpacks verified base and exact7APKs, installs
with standard APK signatures and repository access disabled, creates basic
chroot devnodes, mounts read-only proc/sysfs, checks base ELF hashes/package
versions and traced child, and verifies outer PID1/mounts/boot unchanged.
--verify checks existing package/base/mount state and writes only RAM trace;
initial host staging also creates RAM files. No new services or driver loads.

New prepare_alpine_runtime_stage.py validates base signature receipt/pinned
archive, filtered7APKbundle/memberhashes+matching successfulofflineVM, packs
actualsource/specs/checksums and private inputs, optionally runs cold exact-
stockkernel VM with staticV19outerBB, noNIC/disk. FirstVM
artifacts/alpine-runtime-stage-1792181938707011626 installed/verified packages
but final fixture free outside PATH killed VMinit; failure retained. Corrected
explicitAlpineBBprobe; VM-only EXITpoweroff trap and streaming console capture
added. Defensive shell checks changed from AND-lists to independent checks so
set-e cannot skip a root/input-symlink refusal. Observability source hardened
similarly; no service restart needed.

ColdVM1792182067017586771 passed8checks in8.78s; expandedVM1792182224695177330
passed11checks in9.08s, adding wrongboot/symlinkinput/tamperedinput refusal.
Actualstage script installed/verified, refused existingrootfs and preserved
outerPID1+fixtureprocess; fixtureisnot thermalwatcher/hardwaredriver proof.

New configure_alpine_runtime.py requires matching VM console/kernel/current
input+source bytes, verifies nativepowerbefore/after, pins boot, requires
battery<35C/>=20percent/chargeronline0, tracks all3watcherPIDs. New RAM inputs
hashed before extraction; later reuse requires exactmanifestandallfilehashes.
Refuses partial/mismatched state, preserves failures, no cleanup/shutdown.
Install mode emits compatible rootfs-trial receipt for lynx-alpine wrapper.
Default no contact. Hostwrapper initialattempt1792182105396077127 failed before
contact on relative session path vs childcwd; fixed resolve beforelaunch.
Second1792182118685111977 stopped afterread-onlypreflight on missingioimport,
beforeupload. Bothrawreceiptsretained. Correctednativeverify
logs/alpine-runtime-verify-1792182146999702470 SUCCEEDED; existingrootfs not
reinstalled/newmountsnotcreated. Reuse1792182198922562268 SUCCEEDED without
reupload. All3watcherPIDs unchanged. Input RAMdir
/run/lynx/alpine-stage-231af54bb4b8a034a2f0; retainedinputtar costs extra5MiB.
Offlineverifiedstageinputtests1792182105649581952 accepted valid and rejected
failedVM/changedconsole/sourcehashmismatch.

resume_battery_session.py optional --alpine-stage-receipt requires
--runtime-power, validates offline beforelistener, forwards flag toworker,
starts hostlogger BEFORE optionalLinuxwallclocksync(noRTCwrite) and Alpine
--install. Default previousbehaviorretained. Failed laterstage recordsfailure
withoutstopping existingSSH/watchers/logger. Fixture
artifacts/alpine-resume-sequence-1792182261633323623 passed13checks: default,
success, clockfail, Alpinefail, loggerreceiptretention, ordering, detached
flagpropagation. It starts no realsubprocesses, not hardwarestartup evidence.
FULL COMBINED FRESHBOOT HARDWARE SEQUENCE REMAINS UNTESTED. Do not reboot
usefulsessionjusttotest. ColdinstallpassedVM; existing-rootfsverify/reusepassed
phone. Those are distinct proofs, not a new handsetPID1boot.

### Development userspace, checkpoint recovery, and unattended continuation

In the same verified handset boot cf5e2ccf-5c49-485e-9403-b12e3d6bb574, the
RAM Alpine chroot received signed Python 3.14.8, Git 2.54.0 and Make 4.4.1.
All 23 pre-existing packages were pinned; the final environment had 49 packages
and used about65.4MiB. Python's AArch64, OpenSSL, SQLite and thread checks
passed, as did Git/Make version execution. The `/run` tmpfs limit was safely
raised from128 to256MiB to provide headroom. Original BusyBox PID1 and the
three thermal/battery watchers remained live at the time of installation.
Evidence: `logs/live-alpine-development-1792183223446552019/`.

The development rootfs was volatile and disappeared after Lynx left that
session. The earlier base-only checkpoint at
`checkpoints/alpine-runtime-1792183113469592155/` remains on Nexus; it has
10,082,382 compressed bytes and SHA
8777d923ad8473066026d2a62f3c050581be4b28c5bfa53d0dde0e9a8c83559c. The new
`tools/test_alpine_checkpoint_restore.py` reconstructs members in memory,
checks archive paths and parents, builds an initramfs without host extraction,
then boots the exact stock kernel in a NIC/disk-free QEMU VM. After correcting
CPIO parent ordering, the base checkpoint matched its saved APK/world
inventory byte-for-byte and powered off cleanly:
`linux-port/artifacts/alpine-checkpoint-restore-1792234450094278990/`.
This is a tested restore on Nexus, not a handset boot. Earlier failed
reconstruction attempts and logs remain preserved.

The user reached Fastboot, then proceeded through Orange State into normal
boot and stepped away. No flash or reboot command was issued. To resume without
physical interaction, a guarded 600-second identity-beacon listener was
started through `tools/resume_battery_session.py --start --runtime-power`
with the already VM-verified Alpine stage. Launcher/worker receipt:
`logs/battery-resume-1792234503946756474/result.json`; listener receipt:
`logs/gauge-identity-trial-1792234504186045668/result.json`. It is waiting for
Lynx's native identity beacon. If that workflow reaches its guarded online
state, `tools/continue_alpine_development.py --resume-receipt ...` runs the
fresh battery/thermal checks, reinstalls Python/Git/Make, executes the
read-only Python report, checkpoints the resulting rootfs, and validates that
development checkpoint under QEMU. Each step saves captures and stops on an
unexpected state. No unconditional shutdown, partition change, slot change or
bootloader/recovery operation is part of it.

Finalhealth logs/live-alpine-stage-final-health-1792182291044366468 sameboot,
PIDs17580/18190/25373, battery22.2C/80percent/-101mA/noerrors, SoCsoftwatch
29.463C, run33920KiBfree. Host4hrlogger continues. ExistingV19/stockundo/slotB/
recovery unchanged and globalLinuxflashholdactive. See ALPINE-RUNTIME-STAGE.md.

Final wrapper review added an explicit tmpfs/non-symlink parent check BEFORE
upload (rather than relying only on the stage after upload), plus dangling
symlink refusal for new staging/archive paths. Live verification against the
expanded successful VM receipt passed again at
logs/alpine-runtime-verify-1792182448802972450, reusing verified inputs and
preserving watcher PID inventory. No fresh installation or reboot occurred.

### OpenRC handoff gate built offline

Found a real ordering gap: the proven V19 boot starts Wi-Fi/SSH, while battery
and thermal watchers are installed later by separate host workflows. The V19
contact marker therefore cannot safely authorize an immediate PID 1 change.
Added an opt-in gate that leaves BusyBox as PID 1 until the host's sensor,
battery, and runtime-power stages have completed and current readings pass.
The guard checks matching tokens, exact watcher script hashes and live command
lines, battery monitor/gauge availability, a recent clean sample (<35C and
>=20% charge), complete CPU/SoC sensors (<40C), and the three expected cooling
controls. The host armer verifies the same live guard and boot ID before it
atomically creates the marker.

`tools/build_openrc_gated_candidate.py` created a local-only 64 MiB V20 image
at `linux-port/artifacts/openrc-gated-v20-guardv6/`, SHA256
53156a5f9722eb799f2e27c777d3f63a143fbde339851a3f81683bb0bf9a2dad. It embeds
the verified Alpine/OpenRC root and keeps the existing V19 kernel, boot layout,
and native network startup. The 16,686,490-byte payload fits the existing
40,000,000-byte exclusive bound. Candidate inherits private Wi-Fi/SSH
credentials, mode 0600; binary candidate and fixtures remain ignored local
artifacts. Existing V19 and stock restoration files were not changed.

Offline checks passed: synthetic guard tests at
`artifacts/openrc-handoff-guard-check-1792238268512849510/`; receipt checks at
`artifacts/openrc-handoff-armer-check-1792238268802038131/`; the production
handoff shell (test-only passing guard fixture) booted OpenRC as PID 1 under
the exact V19 kernel, preserved an early worker, ran its test service, and
powered off in QEMU at
`artifacts/openrc-pid1-handoff-vm-1792238374125268640/`. No phone contact,
boot, reboot, or partition write occurred. The combined fresh-boot sensor +
battery + runtime-power sequence and a real handset OpenRC handoff remain
untested. OpenRC does not yet supervise Lynx Wi-Fi/SSH itself. Keep the flash
hold and require a separately supervised hardware trial after the candidate
and restoration procedure are reviewed.

Added `tools/run_openrc_handoff_sequence.py` as a one-command host coordinator
for a future boot of this exact candidate. It serializes pinned contact, the
RAM-only SoC sensor/watch trial, the existing battery/runtime-power resume,
and the OpenRC gate armer; it preserves per-stage receipts and performs no
flash or reboot. Local preflight/self-test passed. It will not be started until
the candidate is actually booted, which is not the current phone state.

### 2026-10-17 V19 contact and active-listener correction

After Noob reported Orange State with USB connected, no phone USB endpoint was
visible. A gauge identity trial listener was mistakenly described as read-only
and started without `--keep-running`. It received a V19 beacon about 80 seconds
later and proved pinned native SSH. The tool then armed its stop timer, loaded
the prepared sensor/CPU modules into RAM, queried gauge DeviceType 0xa5ff,
captured diagnostics, and requested power-off. CPU guard maximum was 37.678C;
battery temperature was not measured. Noob had reported a black screen before
the beacon; the later power-off SSH command timed out, so physical power-off
remains unconfirmed. No flash or partition write occurred. Complete record:
`docs/CONTACT-20261017.md` and
`logs/gauge-identity-trial-1792252324319555253/result.json`.

The active gauge launcher now requires `--run-supervised-trial`; the established
continuous battery-resume caller passes that explicit flag. New
`tools/lynx_identity_observer.py` listens for a beacon and runs only the pinned
read-only SSH proof. Python compile, launcher refusal, passive-listener smoke,
and 13-case offline resume sequence passed. No listener owns port 5514 now.
V19 remains the last recorded `boot_a` write and the Linux flash hold remains
active. Do not infer present physical mode from the black screen.

Later passive observer `logs/identity-observer-1792252530301958299/result.json`
proved a fresh V19 boot with pinned SSH and no phone write/power command. New
boot ID `54d9635c-1193-4161-8393-58ae455aeee2`, uptime 159.85 seconds in
`logs/post-trial-readonly-1792252584897085117/`, establishes a boot after the
diagnostic's power-off request. Cause of restart versus USB startup is unknown.
At uptime 189 seconds host confirmation was absent; SSH still answered at
uptime 261 seconds and later timed out. No phone USB/Fastboot endpoint appeared.
Current physical mode awaits Noob's screen report. Do not claim power-off or
Fastboot without that evidence.

The incident also exposed an ignored physical precondition: the short trial
was reviewed for a USB-unplugged phone, but USB was connected. The active
gauge launcher, direct sensor trial, battery-resume coordinator, and V20
OpenRC coordinator now require `--usb-unplugged-confirmed` before a live run.
Four offline refusal checks passed without contacting Lynx; the revised
14-check resume fixture and V20 offline self-test passed. The flag requires a
current human observation, not an electrical measurement.

Lynx subsequently enumerated as USB `0e8d:201c` on bus001/device005. A
device-specific ACL allowed the fixed read-only Fastboot preflight:
`logs/fastboot-preflight-1792252863616678507.json`. Product, unlocked state,
slot A, bootloader, bootable-slot flags, partition sizes and download limit
all matched. No write/reboot/slot command was issued. Current observed mode is
Fastboot; last recorded installed `boot_a` remains V19, and the global Linux
flash hold is still active.

Read-only LK export `logs/pllk-1792252927082455922.json` returned successfully
with raw output retained. NONRST_REG2=0x28002003, watchdog status0x2, and LK
boot mode99 match previous supported bootloader-return signatures. This
supports V19's unacknowledged-boot fallback as the path to Fastboot; the raw
label says `rst from: lk`, so do not claim exact reset origin beyond the
recorded fields. No further phone command was issued.

### V21 OpenRC candidate built offline; V20 superseded

Review of V20 found that a failed post-contact sensor/battery stage could
leave BusyBox running indefinitely after its 30-minute gate wait. No V20
hardware trial was run. The builder now produces local-only V21 from unchanged
V19 with a 180-second post-contact gate deadline and one supported Fastboot
return request on gate/handoff failure. V19's original Wi-Fi failure path
retains its own one-reset behavior. Candidate SHA256
23fec5b5f319dfcd5bf8555478f843cd7bb9be3a902afc8061ea09c8a0457e4f;
64 MiB; private mode0600; supplement16,686,499bytes under40,000,000. Stock
undo and V19 remain unchanged. Tests passed: exact packed init failure paths
and live shell timeout fixture
`artifacts/openrc-failclosed-check-1792253102353807990/result.json`, guard
fixtures, armer receipts, contact/sequence self-tests, and exact-stock-kernel
production handoff VM
`artifacts/openrc-pid1-handoff-vm-1792253064445885469/result.json`.
No phone contact or partition write occurred for V21. Flash hold remains active;
OpenRC Wi-Fi/SSH supervision and full hardware sequence are still untested.
