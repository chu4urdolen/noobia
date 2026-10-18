# Lynx self-booting Alpine work — 2026-10-18

## V25d supervised trial preparation

### First handset result

The scoped V25d `boot_a` write succeeded at
`logs/v25d-boot-a-trial-1792278881690259342.json` after a matching elevated
Fastboot preflight. Only `boot_a` was written, and the host did not reboot the
phone. Noob disconnected USB and booted the candidate; Orange State was
followed by a black screen. The first observer window expired while waiting
for the physical boot. A second bounded observer at
`logs/v25d-selfboot-observer-1792328214465392719/result.json` made repeated
pinned SSH attempts but had no network response during the observed window.
Noob reported Lynx was unplugged and cool. The screen alone does not prove
whether Linux entered PID 1. No candidate health marker or boot log was
retrieved; **V25d self-boot is unproven**.

Noob returned Lynx to Fastboot. Fresh read-only identity, slot and partition
checks passed at `logs/fastboot-preflight-1792328432997881622.json`. A
read-only LK export is at `logs/pllk-1792328442489652812.json` with its raw
and reconstructed text. It reported no clear kernel crash; it does not locate
the userspace failure. At that point Lynx was in stable Fastboot with V25d still on
`boot_a`. Do not repeat the same blind trial. The next image should expose
pinned SSH before starting the new health path, so a supervised run can
capture boot logs even if health startup fails. Leave the general safety hold
active and preserve V19 and stock rollback files.

### V25f diagnostic follow-up

V25e and V25f are separate offline derivatives of the same V23 image. Both
retain the exact V25d stock kernel and supplemental payload; only the primary
`/init` control order changes. V25f brings up the proven V19 Wi-Fi/Dropbear
worker before the automatic health startup, so pinned SSH can retrieve its
boot log even if the health stage later refuses. A separate 180-second timer
requests power-off if healthy startup does not finish. This is a supervised
diagnostic compromise, not a validated unattended safety policy.

V25f image SHA-256:
`e885fb8162e7faf40fba68732fadd77aa3b4328a4b235e4ae4e60873d8feec0d`.
Its builder is `tools/build_selfboot_wifi_first_guarded.py`; the first-contact
collector is `tools/observe_v25f_diagnostic.py`. The image builder audited
every unchanged member and the init shell syntax, order, and hash were checked.
Local Wi-Fi supervisor and health handoff fixtures passed. This does not prove
hardware execution.

The bounded V25f observer was armed before the physical step at
`logs/v25f-diagnostic-observer-1792328720571478398/result.json`. Fresh Fastboot
preflight passed and the single `boot_a` write succeeded at
`logs/v25f-boot-a-trial-1792328726647445482.json`. The host did not reboot
Lynx. After the user-controlled USB-unplugged boot, the first observer window
expired before the physical start. A fresh observer at
`logs/v25f-diagnostic-observer-1792330133084673993/result.json` made repeated
pinned SSH probes but saw no early contact by the 180-second timer window.
No V25f boot log or health marker was retrieved. Do not call V25f working or
start Alpine handoff. The general safety hold remains in effect.

Offline comparison of V19 and V25f showed the same kernel, boot command line,
primary member names, and all shared supplemental file contents. The primary
`init`, its payload metadata, and added supplemental files are the intended
differences. V25f's supplemental archive grew from V19's 12,245,792 bytes to
16,932,434 bytes because it inherited an unused Alpine/OpenRC archive from
V22. This is a plausible early-boot variable, **not a proven failure cause**.
`tools/build_selfboot_compact_health_candidate.py` therefore prepared V25g by
removing only the unused Alpine root archive and OpenRC handoff scripts. The
resulting supplemental archive is 12,483,821 bytes, close to V19's, and its
init, stock kernel and retained supplemental members match V25f byte-for-byte.
V25g image SHA-256 is
`84b037a79eb678524a88e8c66ced214502ea5381193df26e2c7cec024083bebe`.
Its image, init syntax and package round trip passed offline checks. V25g was
subsequently written to `boot_a`, but its boot remains unproven. The immediate
recovery plan is to return to the proven V19 `boot_a`, retrieve any retained
logs and run its supervised RAM health
stage while USB is unplugged. `tools/restore_v19_boot_a.py` provides that
single-partition rescue.

The original V25f SSH observer only tried the prior `192.168.100.7` DHCP
address. It did not listen for the Wi-Fi worker's discovery beacon, so a
different DHCP lease could have produced a false negative. No V25f beacon was
recorded, and this does not prove that one was sent. The revised
`tools/observe_v25f_diagnostic.py` accepts V25f or V25g, binds the pinned
Noobia collector address before reporting ready, records raw beacon hashes and
source IPs, and switches its pinned-host-key SSH probe to a valid beacon's
address. Both image/hash/parser self-checks passed offline. A bounded live
V19 control at `logs/v25g-diagnostic-observer-1792332021990107978/` received
a valid beacon directly from Lynx and recorded its actual source address;
it deliberately did not claim V25g identity from the running V19 image.

### V19 rescue and live Alpine development — 2026-10-18

Fresh Fastboot preflight at `logs/fastboot-preflight-1792330860405721467.json`
confirmed Lynx's exact identity, unlocked slot A and 64 MiB `boot_a`. The
scoped V19 rescue wrote **only `boot_a`** at
`logs/v19-rescue-boot-a-1792330864189994054.json`; the host left Lynx in
Fastboot. After Noob unplugged USB and booted it, the bounded collector
`logs/wifi-v19-contact-1792330860400042930/result.json` proved the frozen
V19 kernel, `/init`, BusyBox, session token and pinned SSH key, then cancelled
V19's fallback timer. Live read-only `boot_a` SHA-256 matched the full frozen
V19 image: `logs/v19-live-proof-1792331216427841364/result.json`.

The RAM-only autonomous battery, thermal, cooling and health stage passed at
`logs/autonomous-health-ram-trial-1792331061580820074/result.json`. Its
launcher needed a local manifest fix: the startup script had gained the
reviewed `--run-local` mode, while the launcher still pinned an older hash.
The launcher now requires the matching V25d package hash and current passing
startup fixture. This was a host orchestration fix; it does not explain the
failed V25d/f boot. A bounded host battery log is at
`logs/battery-session-1792331081735259936/`. The first live reading was
24.6°C, 69%, charger offline, with a healthy cooling check. Automatic
monitoring continues; manual polling is not needed.

The retained `console-ramoops-0` and `pmsg-ramoops-0` captured under
`logs/v25f-retained-pstore-1792331093508648039/` contain the older diagnostic
token `69adf9d14707d848063b861b8f248748`, not a V25d/f local startup
marker. Their age and provenance therefore prevent attributing them to the
failed self-boot trials. The V25d/f failure point remains unknown.

While V19 stayed live, the signature-verified Alpine 3.24.2 ARM64 minirootfs
was uploaded and run in a RAM chroot. Native shell and APK passed at
`logs/v19-alpine-live-1792331290023858449/result.json`. The Linux wall clock
had to be set from Nexus once, without writing the RTC, at
`logs/v19-clock-sync-1792331336853551341/result.json`. The mini-rootfs lacked
`/etc/resolv.conf` and `/dev/null`; after placing those in the RAM rootfs,
APK installed Python 3.14.8, Git 2.54.0 and Make 4.4.1. Native execution
passed at `logs/v19-alpine-development-proof-1792331428828737536/result.json`.
`alpine-development.sh` now provisions those two RAM prerequisites itself.
The 50 MB private checkpoint is
`checkpoints/alpine-runtime-1792331453858559525/`; an isolated QEMU restore
using Lynx's exact stock kernel passed package/world, Python, Git and Make at
`linux-port/artifacts/alpine-checkpoint-restore-1792331497398834530/result.json`.
This is **Alpine userspace under V19 BusyBox PID 1**, not an automatically
booting Alpine installation or a write to persistent phone storage. The
general self-boot safety hold remains active. At the time of this V19 session,
V25g had not yet been flashed.

Before the hardware write, the V25g trial was prepared offline. The flasher
`tools/flash_v25g_boot_a.py` validated the exact 64 MiB image, stock undo,
reviewed Fastboot binary and matching OTA receipts at
`logs/v25g-boot-a-trial-1792332345922486275.json`. Its narrow review is
`docs/V25G-TRIAL-EXCEPTION.json`. The live run was required to pass fresh
Fastboot identity/slot checks and arm a beacon-aware V25g observer before a
single `boot_a` write. This offline preparation did not contact or restart
Lynx.
The sequence and V19 rollback are recorded in
`docs/V25G-TRIAL-RUNBOOK.md`.
The V25g supplemental payload was also uploaded to a temporary V19 RAM
directory and checked with Lynx's own BusyBox `gzip` and `cpio` tools at
`logs/v25g-live-payload-parser-1792332382589515595/result.json`. Its image
and payload hashes matched, the expected Wi-Fi and health scripts were listed,
and the temporary files were removed. This validates BusyBox parsing on the
handset, but it does not simulate early boot or prove the full candidate boots.

### V25g `boot_a` write — awaiting unplugged boot

Noob authorized the prepared trial with “ok go.” Fresh USB Fastboot preflight
matched the exact Lynx serial, product, unlocked slot A, bootloader version and
partition sizes at `logs/fastboot-preflight-1792333610908609861.json`. The
beacon-aware observer was armed first at
`logs/v25g-diagnostic-observer-1792333613469205903/result.json`. The guarded
single `boot_a` write returned success at
`logs/v25g-boot-a-trial-1792333616762100475.json`; the host did **not** issue a
reboot. Fastboot still enumerated on USB afterward, including when the display
was black. The host therefore has protocol evidence of Fastboot even without a
visible Fastboot menu. A fresh observer was armed at
`logs/v25g-diagnostic-observer-1792333989111901562/result.json` before the
unplugged Power-only boot attempt. Lynx's V25g boot behavior is **unobserved**
until that physical boot actually occurs.
No other partition or slot was written. Preserve both V19 and stock restore
images, and do not infer a successful Linux boot from the Fastboot write.

The unplugged V25g trial showed the orange screen, but the renewed observer
recorded no valid beacon or SSH contact in 83 probes. Fastboot subsequently
reconnected with the expected serial, and the guarded V19 rescue restored only
`boot_a` at `logs/v19-rescue-boot-a-1792334760095554872.json`. The host did not
reboot. The ensuing unplugged boot reached authenticated V19 SSH at
`192.168.100.7`; the pinned collector at
`logs/wifi-v19-contact-1792334500503425456/result.json` cancelled its fallback
timer and saved boot, kernel and pstore diagnostics. A read-only expdb prefix
captured at `logs/expdb-prefix-1792335188180891756/result.json` exactly
matched the earlier baseline over the documented ramconsole and pstore regions
(`logs/expdb-compare-1792348053156007594/result.json`). This yields no new
persistent crash trace from V25g; it does not establish where V25g stopped.

At a later orange-screen boot, a fresh V19 listener was armed at
`logs/wifi-v19-contact-1792348069641858485/result.json`. No beacon or SSH
contact appeared in its first five minutes, while the Nexus Noobia network and
gateway remained reachable. The phone-side state needs fresh observation.

### V25h diagnostic and V19/Alpine recovery

V25g's local Wi-Fi supervisor did not send the discovery beacon that its
observer expected, so a changed DHCP lease could have been missed. V25h added
that beacon as the only changed supplemental member, retaining V25g's exact
kernel and init. The source and exact packaged script passed an offline fake
network fixture. V25h was written only to `boot_a` at
`logs/v25h-boot-a-trial-1792348863400477665.json`; its unplugged boot showed
the orange screen but produced no beacon or authenticated SSH through the full
bounded window. See `docs/V25H-TRIAL-RUNBOOK.md`. This narrows the observer
blind spot but still does not identify the boot failure.

The guarded V19 rescue restored only `boot_a` at
`logs/v19-rescue-boot-a-1792350086116109224.json`. The unplugged boot reached
authenticated SSH at `192.168.100.7` and its automatic health stage passed at
`logs/autonomous-health-ram-trial-1792350300055886410/result.json`. The full
Alpine development checkpoint uploaded and extracted into RAM; the first live
probe found a missing `/dev` directory in the archive. A RAM-only repair added
`/dev/null` and verified native Python 3.14.8, Git 2.54.0 and Make 4.4.1 at
`logs/alpine-checkpoint-live-repair-1792350451274224367/result.json`.
`tools/restore_alpine_checkpoint_live.py` now creates `/dev` in the normal
restore path, while preserving the exact checkpoint and stock-kernel VM proof.
This session runs BusyBox PID 1 with Alpine in a chroot and automatic health;
it does not persist on the phone after power-off.

Read-only storage findings are in `docs/PERSISTENT-STORAGE-READONLY-20261018.md`.
The V27a minimal local-SSH candidate prepared from V19 is described in
`docs/V27A-MINIMAL-LOCAL-SSH.md`. It is offline-only and unflashed, preserving
this live V19/Alpine session for useful work.

While V19 remained on SSH, a read-only Linux block-device capture of the
whole `expdb` partition established a usable crash-log extraction path.
See `docs/EXPDB-LIVE-READ-20261018.md`. The complete record again contains
the older diagnostic token and no literal V25d/f local marker; it does not
prove where those trial boots stopped.

On 2026-10-18 the V25d image and exact August stock `boot.img` were
rehashed, and the reviewed Fastboot binary and matching stock OTA signature
receipts were checked by `tools/flash_v25d_boot_a.py`. The offline readiness
receipt is `logs/v25d-boot-a-trial-1792278530724850021.json`. The only
permitted write in that tool is `boot_a`; it intentionally does not reboot
after flashing, because V25d refuses an online charger and USB must be removed
before native boot. The narrow, one-trial review is in
`docs/V25D-TRIAL-EXCEPTION.json`; the general safety hold remains active.

The read-only observer `tools/observe_v25d_selfboot.py` was armed before any
physical step at `logs/v25d-selfboot-observer-1792278552921944267/result.json`.
It discriminates the new `/init` hash from the still-running V19 and saves
raw SSH attempts, timestamps and any successful boot diagnostics. It sends no
acknowledgement to keep the candidate alive. The latest V19 health sample
before this attempt was 23.8°C, 59% battery, and normal thermal/cooling
watchers. A single SSH invocation of the existing `boot-proof-reboot` returned
exit 1 without changing modes; its raw receipt is
`logs/v25d-bootloader-transition-1792278564250461283/result.json`.
Pinned SSH subsequently confirmed V19 was still running. No phone partition
has been written in this preparation. Await the user-observed physical
Fastboot screen and USB connection before any fresh Fastboot preflight.

The installed `boot_a` remains the proven V19 BusyBox Wi-Fi/SSH image. No
partition has been written during this work. The four-hour host logger at
`logs/battery-session-1792276725293904387/result.json` observes the current
unplugged RAM health trial; on-phone thermal, battery, cooling and supervisor
watchers run independently of the logger. The exact August stock `boot.img`,
previously successful Fastboot restore path and V19 image are preserved. The
active `SAFETY-HOLD.json` still forbids a new Linux flash.

## Independent boot sequence under development

V19 currently waits for a Nexus acknowledgement before remaining in BusyBox.
The separate V25d and V26c **offline** prototypes instead use an init-created
per-boot local marker, after the verified stock bootstrap and boot_a supplement
read. They do not require Nexus to acknowledge a successful boot. The intended
sequence is:

1. Frozen V19 stock kernel, matching bootstrap and verified supplement.
2. Refuse a boot with an online charger or no readable charger state, then
   check the reviewed device tree, calibration, gauge topology, and exact
   sensor/CPU module files; start local battery, thermal, cooling and health
   supervision before Wi-Fi. Failed health startup requests power-off and one
   supported bootloader return.
3. Run the unchanged V19 Wi-Fi worker. Require its own successful result,
   interface, DHCP address and a live Dropbear process; failed startup asks
   for one supported bootloader return. A Wi-Fi network is still needed for
   SSH, but no Nexus process is required for the phone to make that decision.
4. V25d remains in BusyBox as rescue PID 1. V26c additionally verifies the
   embedded Alpine/OpenRC root archive and live safety gate, extracts Alpine
   into RAM, binds `/proc`, `/sys`, `/dev`, and `/run`, and replaces PID 1 with
   OpenRC. A refusal before `exec` leaves the monitored BusyBox environment
   running.

V25d image: `artifacts/selfboot-health-v25d-offline/nord3-selfboot-health-untested.img`,
SHA-256 `130d1cab9fdc48fc4ccafba75920d9bfb8a1a1c95f729ccae517ef1a790d7fb5`.
V26c image: `artifacts/selfboot-alpine-v26c-offline/nord3-selfboot-alpine-untested.img`,
SHA-256 `30b0c50be736650dd4728c926f6d1ff384648acc431f149046b00f6bba4b694d`.
Both are private 64 MiB files, inherit V19's network credentials, reuse its
exact kernel and boot header, and leave unrelated boot-image members unchanged.
They are **not installed**. Superseded V25, V25b, V25c, V26 and V26b
prototypes remain locally preserved for audit. V25d moves health before Wi-Fi
and refuses online charging; V26c explicitly catches an OpenRC guard refusal
so BusyBox PID 1 remains the rescue path.

## Verification completed

- The V19 fresh-boot RAM health trial on the actual handset passed:
  `logs/autonomous-health-window-1792276571479014331/result.json`. The
  matching health archive is unchanged in V25d/V26c; the `--run-local` authority
  gate is a new path and remains untried on hardware.
- Host and local health startup fixtures passed with fake devices:
  `artifacts/autonomous-health-start-check-1792278260648743380/` and
  `artifacts/autonomous-health-start-check-1792278260648760482/`. The local
  fixture also refused an online charger before module insertion. The local
  Wi-Fi fixture passed success and one failure-return case at
  `artifacts/wifi-local-supervisor-check-1792277774233011434/`. The local
  archive handoff fixture passed success, wrong hash and missing marker at
  `artifacts/autonomous-health-local-check-1792277789934091154/`.
- The host and local OpenRC safety guard passed thirteen synthetic checks,
  including missing local health/SSH markers, stale battery, gauge error,
  high temperature and missing cooling controls. The exact source test is
  reproducible with `tools/test_openrc_handoff_guard.py`.
- The V26c local handoff script passed an exact-stock-kernel QEMU run at
  `artifacts/openrc-pid1-handoff-vm-1792277992464569388/result.json`:
  BusyBox early init, local guard fixture, Alpine OpenRC as PID 1, preserved
  early worker, health service adoption, and clean shutdown. QEMU substitutes
  fake sensors and does not exercise Lynx's radio or the complete V26c image.
- The exact V26c init tail was extracted from its image and a refused handoff
  was injected under shell fail-fast mode. BusyBox stayed in the explicit
  rescue path: `artifacts/openrc-local-rescue-check-1792278292357322614/`.
  This is an offline control-flow test, not a handset failure trial.
- Both builders round-trip audited every primary and supplement member and
  rejected changed base-image hashes. The packed init and added scripts passed
  shell syntax checks. These are packaging and control-flow checks, not a
  handset boot proof.

## Persistence and recovery boundary

The V26c Alpine root is an immutable, verified payload in `boot_a`, extracted
into RAM each boot. This lets a fixed release survive power cycles but does
**not** retain package installs, logs or user data. The currently observed
`userdata` partition (`sdc85`, 238,605,533,184 bytes) has unknown contents;
its first 4096 bytes were neither an obvious ext4/F2FS superblock nor all
zero. Do not infer that it is empty. Neither `userdata`, `super`, GPT, slot B,
the bootloader, nor recovery foundations should be changed to create storage
without a separate read-only identification, a restorable backup, and a
reviewed filesystem plan. No persistent-storage write has been made.

V26c still inherits the early BusyBox Wi-Fi and Dropbear processes. Their
survival across PID 1 replacement passed in a VM with a generic worker, but
automatic on-phone restart if either dies is not built yet. Native charging,
charge termination and disconnected-network behavior are not validated.
Before any controlled `boot_a` trial, review those failure paths, validate the
exact V26c image against the current Fastboot device identity and stock undo,
arm a phone-contact collector **before** physical reboot, and keep USB
unplugged. If the phone or recovery behaves unexpectedly, stop rather than
switching slots or changing additional partitions.
