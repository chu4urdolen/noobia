# Lynx Bluetooth NRP/1 service boundary

## Proven base

V52's stock shared-radio calibration and `/dev/stpbt` work. A bounded,
RAM-only H4 bridge registers a standard `hci0` through the kernel's built-in
`N_HCI` line discipline. A narrow capability correction clears only the
controller's false synchronization-train claim. BlueZ then enumerates and
powers on the controller. The bridge can apply Lynx's read-only factory
address to controller RAM before registration. The exact trial and recovery
receipts are in [the connectivity report](LYNX-CONNECTIVITY-PRECAL.md).

The original bridge trial ran for at most 20 seconds. BlueZ and D-Bus remain
disabled at boot. A separate OpenRC service now runs bounded same-boot GATT
trials; it is still disabled at boot.

## Service design

1. Keep the existing V52 boot image and Wi-Fi/SSH independent of Bluetooth.
   Build a separate OpenRC `lynx-bluetooth` service, disabled by default until
   cold-boot tests pass. Its STOP command must close the PTY and `/dev/stpbt`,
   power off the controller, stop its BlueZ child, and restore the previous
   firmware search path.
2. Store the seven matching August firmware files under a root-owned Lynx
   service directory with a manifest of SHA-256 hashes. Verify all hashes
   before opening the radio. Use a private mount namespace for `devpts` and
   keep the one-bit capability correction explicit and audited.
3. Read the factory Bluetooth address from `nvdata` through a transient
   read-only, `noload` mount in that private namespace. Apply it to controller
   RAM before registering `hci0`; verify the result. Never modify `nvdata`.
4. Expose NRP/1 through a Lynx-specific GATT service with a write request
   characteristic and a read reply characteristic. Reuse the NRP/1
   wire grammar, native IDs, VM, sequencer, and thread classes already served
   over Wi-Fi. Do not create a separate runtime instance with different VM
   state. Add a local Unix socket to the existing `lynx-noobd` process so the
   Bluetooth service can pass complete request lines to that same runtime.
5. Bound each signed BLE request to 512 bytes, one line, and a five-second
   assembly timeout. Fragment requests into ATT writes and read replies with
   GATT offsets. Tag every reply with its NRP/1 request ID. Reject malformed
   frames before invoking a native call. Keep pairing disabled; a peer MAC by
   itself is not authentication.

Iris uses the inverse direction: she is a BLE client of a Nexus-hosted GATT
service using the Noobian UUID family. That service's bridge has one
notification socket and is built around Iris. Lynx should not attach to it
as a second client until multiplexing and peer identity are explicitly
implemented. Matching the **NRP/1 protocol** does not require sharing one
GATT connection or one VM instance.

The root-only Unix socket is now installed at `/run/lynx/noobd.sock` in the
**same** `lynx-noobd` process as the Wi-Fi endpoint. The guarded V52 install
verified a local `PING`, Nexus TCP `PING`, and healthy services without a boot
partition write. Receipt:
`lynx/logs/v52-noob-local-socket-1793386552572118101/result.json`.
The prior runtime and OpenRC script are saved on Lynx as `.before-local-socket`.

`tools/lynx_ble_gatt_probe.py` first exposed read-only `PING` and `INFO`.
The bounded initial trial registered this service with BlueZ, and Nexus
discovered, connected without pairing, and exchanged `PING`/`PONG`. The trial
stopped BlueZ and D-Bus, restored the firmware search path, canceled its reboot
watchdog, and found Alpine healthy. Receipt:
`lynx/logs/v52-bluetooth-hci-1793387060460429646/result.json`.

The GATT endpoint is still disabled at boot. It now holds response state per
BlueZ device path, with a 30-second expiry. The phone's stock and V50 rollback
images were not touched.

A persistent-service candidate is installed in `tools/lynx_bluetoothd.py`,
`tools/lynx-bluetooth-openrc.sh`, and
`tools/lynx-bt-firmware-sha256.json`. It verifies the V52 boot image and all
seven August firmware hashes, reads the factory address from a no-replay
read-only mount in a private mount namespace, checks battery and temperature,
and orders GATT, BlueZ, and bridge shutdown. The bridge and GATT application
can now run until SIGTERM. Two consecutive guarded same-boot trials started
the OpenRC service, completed an unpaired BLE `PING`/`PONG`, stopped the
service, verified `hci0` disappeared and Alpine stayed healthy, and canceled
the reboot watchdog. Receipts:
`lynx/logs/v52-bluetooth-service-1793387841289277717/result.json` and
`lynx/logs/v52-bluetooth-service-1793387879934353074/result.json`.
After correcting NRP `INFO`'s old `alpine-v50` label to `alpine-native`, a
third guarded cycle completed both `PING` and the longer `INFO` reply over
BLE, then stopped cleanly. Receipts:
`lynx/logs/v52-noob-info-1793388045443552045.json` and
`lynx/logs/v52-bluetooth-service-1793388079764856722/result.json`.
The passive install receipt is
`lynx/logs/v52-bluetooth-install-1793387653308913027/result.json`.
**The service is still disabled at boot.** Cold-boot, sustained battery use,
and automatic recovery after a child crash remain unverified.

## Nexus-issued controls and audible VM trial

`tools/lynx_ble_auth.py` signs the exact NRP/1 request with HMAC-SHA256, a
fresh 32-byte challenge, and a strictly increasing sequence number. It rejects
malformed, oversized, tampered, and repeated frames. The root-owned Lynx key
at `/etc/lynx/nrp-nexus.key` and the Nexus key under `lynx/private/` are
mode 0600; the key is ignored by Git and has never been logged. Wi-Fi TCP uses
the same signature plus its Nexus source-IP restriction. The local root-only
Unix socket remains available to Lynx processes, and BLE forwards accepted
commands to that *same* runtime. Controls are therefore available remotely
only to a holder of the Nexus key, while local root can still issue commands.

The guarded install receipt is
`lynx/logs/v52-nexus-issuer-1793389116664130594/result.json`. It verified
authenticated TCP `PING`, `INFO`, and VM status, and rejected unsigned TCP.
The first guarded BLE trial rejected an unsigned request, ran a one-byte HALT
VM, reset it, and stopped with healthy Alpine:
`lynx/logs/v52-bluetooth-service-1793389134959764392/result.json`.

The audible trial in
`lynx/logs/v52-bluetooth-service-1793389426154835667/result.json` sent one
authenticated `CALL_MIXED SOUND_PLAY "beep"` command, then loaded and ran a
24-byte VM program that called native `SOUND_PLAY` twice with a 1200 ms wait.
The VM halted, its return register was 1, and `RESET_VM` restored EMPTY. Noob
reported hearing all three beeps. The service stopped, `hci0` disappeared,
Alpine health passed, and the watchdog was canceled. An earlier attempted
audible trial used an unquoted sound name; Lynx rejected it before playing,
and its guarded teardown also passed. No boot partition was written.

Audio had been stopped when the test began. `rc-service lynx-audio start`
loaded the existing MT6983 card and firmware, and `AUDIO_READY` returned
`card=1 firmware=1` before the audible trial. Keep this as a preflight for
later sound tests.

## Reconnect and supervisor trials, 2026-10-30

The initial live GATT endpoint kept one authentication sequence for the
entire service run. That prevented a fresh BLE connection from starting at
sequence 1. `AuthSessions` now issues a new challenge per BlueZ device path
on an offset-zero challenge read, expires idle sessions, rejects old signed
frames, and clears the prior response on renewal. The guarded update receipt
is `lynx/logs/v52-bluetooth-sessions-1793391156888664724/result.json`;
the previous GATT file is saved on Lynx as
`/usr/local/bin/lynx-ble-gatt.before-reconnect`.

A guarded live trial disconnected and reconnected in the same service run.
It observed a fresh challenge, rejected the old signed frame, and found the
loaded VM still `READY`, then ran and reset it. Service STOP removed `hci0`
and Alpine stayed healthy. Receipt:
`lynx/logs/v52-bluetooth-service-1793391163649963019/result.json`.

OpenRC now uses `supervise-daemon` for `lynx-bluetooth`, with an eight-second
restart delay and at most three attempts per ten minutes. The old init script
is `/etc/init.d/lynx-bluetooth.before-supervisor`; update receipt:
`lynx/logs/v52-bluetooth-supervisor-1793391316090072184/result.json`.
A guarded trial stopped the GATT child. The service restarted, accepted a
fresh authenticated VM reconnect, then stopped cleanly with Wi-Fi, SSH, and
Alpine health intact. Receipt:
`lynx/logs/v52-bluetooth-service-1793391400834625283/result.json`.

**The reboot trial was inconclusive because its timers were too short.** A one-shot 180-second boot guard
and `lynx-bluetooth` were added to the default OpenRC runlevel, then `reboot`
was sent. Alpine/SSH did not return within the trial's 125-second window;
the live rollback attempt could not connect. No partition was written. The
user subsequently reported Lynx in Fastboot without USB, hours after the
test. The boot guard cannot run while the phone is in Fastboot. Receipt:
`lynx/logs/v52-bluetooth-reboot-1793391583551810582/result.json`.
After USB reconnection, read-only Fastboot queries still reported the
expected product, slot A, `slot-successful:a=yes`, `slot-unbootable:a=no`,
and retry count 7. One `fastboot reboot` was accepted, but Alpine/SSH did not
return within 100 seconds; the phone also was not enumerated in Fastboot at
the end of the wait. No partition was written. Recovery attempt receipt:
`lynx/logs/v52-bt-fastboot-recovery-1793445997609440027/result.json`.
The recovery boot image and slot B were not changed by these Bluetooth trials.

### Recovery result, 2026-10-31

The verified V50 image was restored to **boot_a only**, with receipt
`lynx/logs/v52-boot-a-trial-1793446431457649292/result.json`. The first
100-second SSH wait after `fastboot reboot` still expired, but Lynx later
appeared on Wi-Fi with a new V50 boot ID. The Nexus monitor read 25% battery
at that point. On Alpine, `boot_a` matched V50's SHA-256, health reported no
issues, and Bluetooth was stopped and absent from the default runlevel.
The one-shot boot guard was also removed. Its persistent log confirms that it
timed out during the prior V52 boot, removed Bluetooth from the default
runlevel, stopped the service, and requested a reboot. This explains why
Bluetooth was already boot-disabled on V50.

The archived V52 boot log shows Wi-Fi's local SSH check passing at uptime
39.66 seconds, health passing at 201 seconds, and the persistent Alpine PID1
handoff beginning at 211.53 seconds. The first reboot trial stopped polling
for Alpine SSH after 125 seconds, and the later Fastboot recovery script
stopped after 100 seconds. Both windows ended **before** the documented Alpine
handoff. V52's power history showed 88% battery during the guard interval;
the later 25% reading belongs to the V50 recovery boot, after intervening
hours. We therefore have no evidence from these timers that Bluetooth made
the V52 boot fail. The detailed read-only log copy is
`lynx/logs/v52-auto-bt-boot-review-1793446970350856614/`.

Future scripts now allow 450 seconds for the Alpine/SSH check and 660 seconds
for the boot rollback guard. These durations have **not** been trialed on
hardware. The radio stays boot-disabled on the restored V50 image until the
next controlled V52 test.

On 2026-10-31, Noob clarified that 25% is sufficient for a trial while 5%
is not. The Bluetooth supervisor's reserve was adjusted to require at least
20% to start and to stop its radio service below 15%, leaving margin above
Lynx's existing critical battery guard. The guarded passive install on V50
did not start Bluetooth or change `boot_a`; receipts:
`lynx/logs/v52-bluetooth-battery-guard-1793447670895867348/result.json` and
`lynx/logs/v52-bluetooth-battery-guard-v2-1793447753633128241/result.json`.
The final threshold has not yet had a V52 radio trial.

### Latest V52 trials, 2026-10-31

V52 was flashed to `boot_a` only and booted from Fastboot into healthy Alpine.
The bounded same-boot service trial passed authenticated PING/INFO, unsigned
request rejection, reconnect with a fresh challenge, VM state preservation,
and clean radio teardown. The first automatic-start reboot reached Alpine and
Bluetooth ready, but Nexus discovery exceeded a 25-second client deadline.
The same-boot rerun passed after allowing 40 seconds for discovery and a
separate GATT-resolution deadline. Receipts:
`lynx/logs/v52-bt-fastboot-recovery-1793448380509660010/result.json`,
`lynx/logs/v52-bluetooth-service-1793448698158063611/result.json`, and
`lynx/logs/v52-bluetooth-service-1793449310204055874/result.json`.

An integrated first-boot guard then passed a 15-second live test: it started
from OpenRC `start_pre`, disabled Bluetooth autostart, stopped the radio, and
left Alpine healthy. Receipt:
`lynx/logs/v52-bt-integrated-guard-1793449522329594978/result.json`.
The subsequent automatic-start reboot did **not** reach Alpine SSH. Nexus
passively observed USB Fastboot after about five minutes; read-only Fastboot
queries reported slot A still bootable. No new Alpine power-history boot ID or
pstore record exists for that attempt, and the guard log contains no start
entry from it. This does not locate the failure within the kernel/boot chain,
and it does not prove Bluetooth caused it. Receipt:
`lynx/logs/v52-bluetooth-reboot-1793449551490815372/result.json`.

The verified V50 image was restored to `boot_a` only and booted to healthy
Alpine/Wi-Fi. Its boot hash matches V50, Bluetooth is stopped and absent from
the default runlevel, and the trial marker is absent. Receipt:
`lynx/logs/v52-bt-fastboot-recovery-1793449933925684721/result.json`.
The Nexus presence monitor saw V50 on Wi-Fi after that recovery. A later
trial used OpenRC's graceful shutdown path and a host-side USB Fastboot
observer, as recorded below.

### Graceful reboot trial, 2026-10-31

USB Fastboot preflight initially timed out because the script used an
unprivileged USB command while the current device node required `sudo -n`.
That attempt made no partition write. The preflight and V52 boot_a trial now
use the same noninteractive sudo path; the repeated full preflight passed.
V52 was flashed to `boot_a` only and booted into healthy Alpine/SSH with the
expected hash, battery 29%, and Bluetooth disabled. Receipts:
`lynx/logs/v52-boot-a-trial-1793450533301121989/result.json`,
`lynx/logs/v52-boot-a-trial-1793450572899829185/result.json`, and
`lynx/logs/v52-boot-a-trial-1793450578523983243/result.json`.

With Lynx later at 44% battery, the guard script gained a start record and
was installed without starting the radio or changing `boot_a`:
`lynx/logs/v52-bluetooth-boot-guard-script-1793463900594513194/result.json`.
The automatic-start trial armed the 660-second guard, added Bluetooth to the
default OpenRC runlevel, and requested a graceful `openrc-shutdown -r now`.
Nexus then observed USB Fastboot before Alpine SSH. The guard has no new
start entry; Alpine power history has no new boot ID for the failed attempt.
This second failure with a different reboot command makes the earlier direct
`reboot` call an insufficient explanation. It still does not prove precisely
where boot stopped or that the radio driver ran. Receipt:
`lynx/logs/v52-bluetooth-reboot-1793463917883713251/result.json`.

V50 was restored to `boot_a` only and returned to Alpine/SSH with 44% battery.
The Bluetooth runlevel link and marker were removed. The recovery helper's
immediate final health assertion caught a brief `lynx-health` restart at
uptime 230 seconds and reported failure; a later read-only check at uptime
244 seconds confirmed V50's boot hash, healthy services, Wi-Fi, absent marker,
and stopped Bluetooth. The helper now separates cleanup from a bounded
settled-health check. Receipts:
`lynx/logs/v52-boot-a-trial-1793464180420430243/result.json` and
`lynx/logs/v52-bt-fastboot-recovery-1793464186134310110/result.json`.

The next startup design should keep `lynx-bluetooth` out of OpenRC's default
dependency graph until persistent Alpine is healthy. Test delayed local start
with a rollback timer on a V52 boot, then test autonomous startup separately.
After V50 recovery, `/sys/fs/pstore` was empty and the checked boot-reason
paths exposed no readable record. The persistent guard log also lacked a
start line for the failed V52 boot. The last kernel messages were from the
successful V50 boot; they do not identify the prior reset cause.

`tools/trial_v52_bluetooth_after_alpine.py` is the staged next trial. Its
default mode is read-only. `--start` requires the exact V52 boot hash, at
least 240 seconds of Alpine uptime, healthy Wi-Fi/Noobian services, battery
at least 20%, and no Bluetooth default-runlevel link. It arms a bounded
reboot watchdog, starts Bluetooth only after those checks, verifies signed
BLE reconnect and VM continuity from Nexus, samples health for 1–15 minutes,
then stops the radio and cancels the watchdog after teardown. The optional
`--leave-running` keeps the service on only after a successful sustained
trial. It never changes an OpenRC runlevel or partition. On the current V50
boot its read-only preflight refused the V52 identity with no radio start:
`lynx/logs/v52-bt-after-alpine-1793465203090081096/result.json`. The live
V52 path remains untested.

### V52 boot-disabled control, 2026-11-01

After an overnight gap, Lynx appeared in USB Fastboot. Fastboot cannot report
a usable battery value on this bootloader, so V50 was booted first. Its live
Alpine health check reported 33% battery, no issues, and the exact V50 boot
hash. The previously tested freestanding ARM64 RESTART2(`bootloader`) helper
was staged in RAM with its SHA-256 checked, invoked once after `sync`, and
returned to verified USB Fastboot in about ten seconds. The helper wrote no
partition. Receipt:
`lynx/logs/v50-alpine-fastboot-return-1793528329961324836/result.json`.

The exact V52 image was then flashed to `boot_a` only and rebooted with
`lynx-bluetooth` **absent** from the default runlevel. Nexus observed USB
Fastboot again at roughly 242 seconds; there was no Alpine SSH and no
Bluetooth service trial. The observation persisted through 278 seconds.
V50 was restored to `boot_a` only, rebooted, and verified healthy with
Bluetooth autostart absent. Receipts:
`lynx/logs/v52-boot-a-trial-1793528347221672615/result.json`,
`lynx/logs/v52-boot-a-trial-1793528352107833993/result.json`,
`lynx/logs/v52-boot-a-trial-1793528644442104287/result.json`, and
`lynx/logs/v52-bt-fastboot-recovery-1793528649259893639/result.json`.

This control means an OpenRC Bluetooth default-runlevel link is **not
required** for the Fastboot return. Do not retry the unchanged V52 image
merely to test delayed radio startup.

A read-only capture of the first 0xF0000 bytes of `expdb` on recovered V50
found a changed retained pstore region. It contains a trace with V52's two
early Bluetooth module loads, rescue Wi-Fi/SSH readiness, and
`PERSISTENT_OPENRC_PID1_HANDOFF_BEGIN` at uptime 207.46 seconds. The saved
successful V52 boot log from 2026-10-31 recorded that handoff at 211.53
seconds, so this is a different trace. The retained record has no literal
kernel panic or later Alpine event. The static session token and retention
format do **not** prove that it belongs to the immediately preceding failed
boot. Capture and region hashes are in
`lynx/logs/v50-expdb-after-v52-1793528962511434915/result.json`; the raw
capture stays local and private. `/sys/fs/pstore` was empty after recovery.

The current boundary is between rescue's recorded PID 1 handoff and durable
Alpine service evidence. Investigate V52's early BT module effects and add
provenance for that boundary before another image trial. V50 remains the
working system and exact rollback.

`tools/capture_v52_boot_stream.py` is the read-only collector for a diagnostic boot.
Start `--capture` **after** a guarded V52 flash and **before** its Fastboot
reboot. It waits for pinned rescue SSH on port 22, verifies the exact V52
boot hash and BusyBox PID 1, then streams `/dev/kmsg` to Nexus while taking
bounded rescue boot-log snapshots. It observes Alpine SSH and USB Fastboot,
caps the stream at 32 MiB, and never writes to Lynx. Its live test result is
recorded below. Any further V52 boot trial should use this collector and the
verified V50 rollback, with a fresh battery reading, so failures leave a
host-side kernel trace.

### Live stream and delayed Bluetooth pass, 2026-11-01

With V50 healthy at 34%, one diagnostic V52 boot was made through the
verified RAM-only Fastboot return and `boot_a`-only flash. The collector
verified V52 BusyBox rescue at 62 seconds, streamed 1,841,851 bytes of live
kernel messages, and saved rescue boot-log snapshots. This boot recorded
`PERSISTENT_OPENRC_PID1_HANDOFF_BEGIN` at uptime 221.51 seconds, reached
healthy V52 Alpine/SSH at about 249 seconds, and remained healthy for the
collector's additional 30 seconds. Bluetooth was still boot-disabled.
Receipts:
`lynx/logs/v50-alpine-fastboot-return-1793529309517134430/result.json`,
`lynx/logs/v52-boot-a-trial-1793529319461397746/result.json`,
`lynx/logs/v52-boot-a-trial-1793529331256500549/result.json`, and
`lynx/logs/v52-live-boot-stream-1793529324948481541/result.json`.

The delayed trial's read-only preflight then passed. Only after Alpine was
healthy did it start `lynx-bluetooth`, without adding a default-runlevel
link. Nexus completed authenticated BLE PING/INFO and reconnect, rejected an
unsigned command and an old session, and verified VM state across reconnect.
Ten health samples across five minutes reported no issues; battery remained
at 34%, with maximum sampled thermal reading about 37°C. The watchdog was
canceled, and the service was deliberately left running on this V52 boot.
The final read-only check verified the exact V52 boot hash, the same boot ID,
`hci0`, Bluetooth ready, healthy Alpine/Wi-Fi/SSH, no trial marker, and no
Bluetooth startup link. Receipts:
`lynx/logs/v52-bt-after-alpine-1793529607956660475/result.json` and
`lynx/logs/v52-bt-after-alpine-1793529612974351999/result.json`.

**Live state at that checkpoint:** V52 Alpine with Bluetooth running
and V50 preserved as the exact Fastboot rollback. The V52 image has also
returned to Fastboot on a boot with Bluetooth autostart disabled. Therefore
the running service is a working session, while autonomous restart remains
unproven. Keep Bluetooth out of the boot runlevel. Do not infer that every
V52 boot will succeed from this one pass.

### Monitored warm reboot, 2026-11-01

After roughly 45 minutes of healthy V52 Alpine with Bluetooth running,
`openrc-shutdown -r now` was issued with a read-only rescue SSH/kernel stream
collector already listening. Bluetooth remained absent from the boot
runlevel. Lynx returned to USB Fastboot without the collector ever reaching
rescue SSH on port 22. No kernel stream was captured on this boot. This is an
earlier **observable** failure boundary than the retained trace discussed
above; lack of rescue SSH does not prove that Linux PID 1 never executed.
Receipts:
`lynx/logs/v52-monitored-reboot-1793532084119118630/result.json` and
`lynx/logs/v52-live-boot-stream-1793532076594415580/result.json`.

V50 was restored to `boot_a` only and returned to healthy Alpine/SSH, with
Bluetooth autostart absent. A new read-only `expdb` prefix capture matched
the preceding capture's ramconsole and pstore hashes exactly, so it provides
no new trace for this warm reboot. Receipts:
`lynx/logs/v52-boot-a-trial-1793532335520376012/result.json`,
`lynx/logs/v52-bt-fastboot-recovery-1793532340726488244/result.json`, and
`lynx/logs/v50-expdb-after-v52-1793532587861599649/result.json`.

**Current live state after this trial:** verified V50 Alpine/Wi-Fi/SSH;
Bluetooth off. The prior five-minute delayed Bluetooth pass is valid for
that V52 session, but it did not establish reliable reboot. Investigate
warm radio/conninfra reset and early rescue contact before restoring V52
for another sustained-service trial.

Do not enable Bluetooth at boot for normal operation until a guarded reboot
trial verifies Alpine, Wi-Fi, SSH, battery current, and Bluetooth together.
Same-boot Bluetooth, reconnect, and child-crash recovery are proven; automatic
startup is still unverified.

The object tree, registration, advertising, and read/write option contracts
follow the official [BlueZ GATT API](https://bluez.readthedocs.io/en/latest/gatt-api/)
and [Advertising API](https://bluez.readthedocs.io/en/latest/advertising-api/).
The Nexus client uses the documented [Adapter](https://bluez.readthedocs.io/en/latest/adapter-api/)
and [Device](https://bluez.readthedocs.io/en/latest/device-api/) methods.

## Acceptance sequence

- Service starts and stops repeatedly on the same boot, leaving Wi-Fi and
  Alpine healthy and no `hci0` after STOP. **Done three times.**
- BlueZ reports Lynx's factory address and the expected power state. A
  same-boot restart did not switch back to MediaTek's placeholder address.
  **Done; cold boot still untested.**
- Nexus discovers the dedicated Lynx service, connects, and completes
  bounded `PING` and `INFO` exchanges without pairing. **Done**, with signed
  commands and an unsigned-request rejection test.
- A simple native call, a VM load/run/status cycle, and disconnect/reconnect
  use the same runtime state seen over Wi-Fi. **Done in guarded same-boot
  trials.**
- A cold boot with the service enabled retains display, battery monitoring,
  thermal limits, Wi-Fi, SSH, and the V50 Fastboot rollback. Any service
  failure leaves SSH available and Bluetooth off.
